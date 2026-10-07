# Generates one Airflow DAG per data product folder in dags/dataproducts/<data-product-id>/.
#
# A folder contains the data product's ODPS file (<id>.odps.yaml), its ODCS data contracts
# (*.odcs.yaml) and optionally a dbt project. Each DAG:
#   1. publishes the semantics namespaces in dags/semantics/, then the ODCS and ODPS files,
#      to Entropy Data
#   2. runs `dbt-ol build` if the folder has a dbt project; dbt-ol sends OpenLineage events to
#      Entropy Data, linked to the data product
#   3. runs `datacontract test` for every output port contract and publishes the results
#
# DAGs are chained along the ODPS input ports: a data product whose input port contract belongs to
# another data product in this folder runs when that data product's DAG has finished (Airflow
# assets). Data products without such inputs run daily.
#
# Credentials come from the executor environment (see platform/manifests/airflow/airflow.yaml):
# ENTROPY_DATA_API_KEY, TRINO_PASSWORD and TRINO_CA_BUNDLE.
from datetime import datetime
from pathlib import Path

import yaml
from airflow import DAG
from airflow.operators.python import PythonVirtualenvOperator
from airflow.sdk import Asset
from airflow.sensors.python import PythonSensor

DATAPRODUCTS_PATH = Path(__file__).parent / "dataproducts"
SEMANTICS_PATH = Path(__file__).parent / "semantics"
ENTROPY_DATA_URL = "http://entropy-data:8080"
VENV_REQUIREMENTS = ["dbt-trino", "openlineage-dbt", "datacontract-cli[trino]"]


def check_entropy_data_ready(entropy_data_url, **context):
    """Wait until the entropy-data-init job has stored an API key and Entropy Data accepts it."""
    import os
    import urllib.request

    api_key = os.environ.get("ENTROPY_DATA_API_KEY")
    if not api_key:
        print("  ENTROPY_DATA_API_KEY not set yet (entropy-data-init job still running?).")
        return False
    try:
        req = urllib.request.Request(f"{entropy_data_url}/api/teams", headers={"x-api-key": api_key})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:
        print(f"  Entropy Data not ready: {e}")
        return False


def publish(folder: str, semantics_folder: str, entropy_data_url: str):
    """PUT the semantics namespaces, then the data product's ODCS and ODPS files to Entropy Data.
    Semantics go first because contracts link to its concepts, contracts before the data product
    because the data product references them."""
    import json
    import os
    import urllib.error
    import urllib.request
    from pathlib import Path

    import yaml

    def put(kind, document):
        put_path(f"/api/{kind}/{document['id']}", document)

    def put_path(path, document):
        req = urllib.request.Request(
            f"{entropy_data_url}{path}",
            data=json.dumps(document, default=str).encode(),
            headers={"Content-Type": "application/json", "x-api-key": os.environ["ENTROPY_DATA_API_KEY"]},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                print(f"  PUT {path} -> {resp.status}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"PUT {path} failed with {e.code}: {e.read().decode()}") from e

    for namespace_file in sorted(Path(semantics_folder).glob("*.yaml")):
        ns = yaml.safe_load(namespace_file.read_text())
        base = f"/api/semantics/experimental/namespaces/{ns['namespace']}"
        concepts, relationships = ns.pop("concepts", []), ns.pop("relationships", [])
        put_path(base, ns)
        for concept in concepts:
            put_path(f"{base}/concepts/{concept['id']}", {"team": ns.get("team"), **concept})
            # Inline properties are created without their IRI, so set it on the property concept itself
            for prop in concept.get("properties", []):
                if "iri" in prop:
                    prop_id = f"{concept['id']}.{prop['id']}"
                    put_path(f"{base}/concepts/{prop_id}", {**prop, "id": prop_id, "kind": "property"})
        for relationship in relationships:
            put_path(f"{base}/relationships/{relationship['id']}", relationship)

    folder = Path(folder)
    for contract in sorted(folder.glob("*.odcs.yaml")):
        put("datacontracts", yaml.safe_load(contract.read_text()))
    for product in sorted(folder.glob("*.odps.yaml")):
        put("dataproducts", yaml.safe_load(product.read_text()))


def dbt_build(folder: str, entropy_data_url: str, data_product_id: str):
    """Run `dbt-ol build` on a private copy of the dbt project (the git-synced folder is
    read-only); dbt-ol ships OpenLineage events to Entropy Data."""
    import os
    import shutil
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    project = Path(tempfile.mkdtemp()) / "project"
    shutil.copytree(folder, project, ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"))
    env = {
        **os.environ,
        "OPENLINEAGE__TRANSPORT__TYPE": "http",
        "OPENLINEAGE__TRANSPORT__URL": entropy_data_url,
        # One dbt run builds all output ports, so the events are linked to the data product only
        "OPENLINEAGE__TRANSPORT__ENDPOINT": f"api/v1/lineage?dataProductId={data_product_id}",
        "OPENLINEAGE__TRANSPORT__AUTH__TYPE": "api_key",
        "OPENLINEAGE__TRANSPORT__AUTH__APIKEY": os.environ["ENTROPY_DATA_API_KEY"],
        "OPENLINEAGE_NAMESPACE": "airflow",
    }
    dbt_ol = Path(sys.executable).parent / "dbt-ol"
    subprocess.run([str(dbt_ol), "build", "--profiles-dir", "."], cwd=project, env=env, check=True)


def datacontract_test(folder: str, entropy_data_url: str, contract_ids: list):
    """Test the output port contracts against Trino and publish the results to Entropy Data."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {
        **os.environ,
        "DATACONTRACT_TRINO_USERNAME": os.environ.get("TRINO_USER", "admin"),
        "DATACONTRACT_TRINO_PASSWORD": os.environ["TRINO_PASSWORD"],
        # datacontract-cli only sends ENTROPY_DATA_API_KEY to the host named here
        "ENTROPY_DATA_HOST": entropy_data_url,
    }
    if os.environ.get("TRINO_CA_BUNDLE"):
        env["REQUESTS_CA_BUNDLE"] = os.environ["TRINO_CA_BUNDLE"]
    datacontract = Path(sys.executable).parent / "datacontract"
    failed = []
    for contract_id in contract_ids:
        result = subprocess.run(
            [str(datacontract), "test", str(Path(folder) / f"{contract_id}.odcs.yaml"),
             "--server", "trino", "--publish", f"{entropy_data_url}/api/test-results"],
            env=env,
        )
        if result.returncode != 0:
            failed.append(contract_id)
    if failed:
        raise RuntimeError(f"Data contract tests failed for: {', '.join(failed)}")


def dataproduct_asset(data_product_id: str) -> Asset:
    return Asset(f"entropydata://dataproducts/{data_product_id}")


def build_dag(folder: Path, producer_by_contract: dict) -> DAG:
    odps = yaml.safe_load(next(folder.glob("*.odps.yaml")).read_text())
    data_product_id = odps["id"]
    upstream = sorted({
        producer_by_contract[port["contractId"]]
        for port in odps.get("inputPorts") or []
        if port.get("contractId") in producer_by_contract and producer_by_contract[port["contractId"]] != data_product_id
    })
    output_ports = odps.get("outputPorts") or []
    contract_ids = [p["contractId"] for p in output_ports if p.get("contractId")]
    has_dbt = (folder / "dbt_project.yml").exists()
    venv = dict(
        requirements=VENV_REQUIREMENTS,
        system_site_packages=False,
        python_version="3.12",
    )

    with DAG(
        dag_id=f"dataproduct_{data_product_id.replace('-', '_')}",
        description=odps.get("name", data_product_id),
        schedule=[dataproduct_asset(u) for u in upstream] if upstream else "@daily",
        start_date=datetime(2024, 1, 1),
        catchup=False,
        is_paused_upon_creation=False,
        tags=["dataproduct", *(["dbt"] if has_dbt else [])],
        default_args={"retries": 2},
    ) as dag:
        wait = PythonSensor(
            task_id="wait_for_entropy_data",
            python_callable=check_entropy_data_ready,
            op_kwargs={"entropy_data_url": ENTROPY_DATA_URL},
            poke_interval=30,
            timeout=1800,
        )
        steps = ["publish"] + (["dbt"] if has_dbt else []) + (["test"] if contract_ids else [])
        # The last step signals downstream data products (see `upstream`) that this one is fresh
        outlets = lambda step: [dataproduct_asset(data_product_id)] if step == steps[-1] else []
        tasks = [wait, PythonVirtualenvOperator(
            task_id="publish_to_entropy_data",
            python_callable=publish,
            requirements=["pyyaml"],
            system_site_packages=False,
            python_version="3.12",
            op_kwargs={"folder": str(folder), "semantics_folder": str(SEMANTICS_PATH), "entropy_data_url": ENTROPY_DATA_URL},
            outlets=outlets("publish"),
        )]
        if has_dbt:
            tasks.append(PythonVirtualenvOperator(
                task_id="dbt_build",
                python_callable=dbt_build,
                op_kwargs={"folder": str(folder), "entropy_data_url": ENTROPY_DATA_URL, "data_product_id": data_product_id},
                outlets=outlets("dbt"),
                **venv,
            ))
        if contract_ids:
            tasks.append(PythonVirtualenvOperator(
                task_id="datacontract_test",
                python_callable=datacontract_test,
                op_kwargs={"folder": str(folder), "entropy_data_url": ENTROPY_DATA_URL, "contract_ids": contract_ids},
                outlets=outlets("test"),
                **venv,
            ))
        for upstream_task, downstream_task in zip(tasks, tasks[1:]):
            upstream_task >> downstream_task
    return dag


_folders = sorted(p for p in DATAPRODUCTS_PATH.iterdir() if p.is_dir() and any(p.glob("*.odps.yaml")))
# Which data product provides which contract, to resolve input ports to upstream data products
_producer_by_contract = {}
for _folder in _folders:
    _odps = yaml.safe_load(next(_folder.glob("*.odps.yaml")).read_text())
    for _port in _odps.get("outputPorts") or []:
        if _port.get("contractId"):
            _producer_by_contract[_port["contractId"]] = _odps["id"]

for _folder in _folders:
    globals()[f"dataproduct_{_folder.name.replace('-', '_')}"] = build_dag(_folder, _producer_by_contract)
