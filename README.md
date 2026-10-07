# Entropy Data dbt Demo on the Stackable Data Platform

> [!WARNING]
> This repository is not meant for the general public, it is public because it may be helpful to some people and definitely serves an instructional purpose, but especially the justfile recipes and scripts in here can cause harm and delete data if not used with caution! 


A GitOps-managed Kubernetes demo that showcases [Entropy Data](https://www.entropy-data.com/) (Community Edition) on the [Stackable Data Platform](https://stackable.tech/), alongside commonly used tools from the wider data ecosystem: Superset, dbt, OpenLineage, Lakekeeper, GarageFS, Kafka, and NiFi.

The demo deploys a complete data lakehouse on Kubernetes, with TPC-H sample data flowing through dbt models in Trino, Iceberg tables managed by Lakekeeper, and S3-compatible storage via GarageFS. Data products are defined as code (ODPS + ODCS + dbt) and published to Entropy Data by Airflow, with lineage from `dbt-ol` and data contract test results, all continuously deployed via ArgoCD.

> This is an adaptation of [stackabletech/openmetadata-dbt-demo](https://github.com/stackabletech/openmetadata-dbt-demo), with OpenMetadata replaced by Entropy Data.

> [!NOTE]
> The OpenTofu configuration in `tofu/` provisions AKS, but the Kubernetes manifests themselves no longer require any cloud-specific storage class. See [Portability](#portability) for details.

## Architecture

```
stackablectl (just deploy)
  └─> installs ArgoCD + bootstrap apps from infrastructure/stack.yaml
        └─> ArgoCD deploys infrastructure/ (Forgejo, SealedSecrets, operators)
              └─> Forgejo mirrors this GitHub repo into the cluster
              └─> cluster-apps.yaml watches platform/applications/ (app-of-apps pattern)
                    └─> each Application in platform/applications/ deploys its manifests
```

All changes flow through Git. ArgoCD has `selfHeal: true` enabled, so any manual changes applied directly to the cluster are reverted automatically.

## How you can use it

### Prerequisites

- An Azure subscription (for AKS provisioning)
- [`az`](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) CLI, logged in
- [OpenTofu](https://opentofu.org/) (or Terraform)
- [`stackablectl`](https://docs.stackable.tech/home/stable/stackablectl/) installed
- `kubectl`
- [`just`](https://just.systems/) (optional, but recommended)

### Provision AKS Cluster

The `tofu/` directory contains OpenTofu configuration to create an AKS cluster with all required networking.

1. Copy the template and fill in your values:

```bash
cp tofu/terraform.tfvars.template tofu/terraform.tfvars
# Edit tofu/terraform.tfvars with your name, subscription ID, and owner
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `name` | yes | — | Name for the resource group and AKS cluster |
| `subscription_id` | yes | — | Azure subscription ID |
| `owner` | yes | — | Owner tag on the resource group and cluster |
| `location` | no | `westeurope` | Azure region |
| `node_count` | no | `3` | Number of nodes in the user pool |
| `node_vm_size` | no | `Standard_D8ds_v5` | VM size for user pool nodes |
| `kubernetes_version` | no | `1.33` | Kubernetes version |

2. Provision the cluster (each cluster gets its own state file `tofu/<name>.tfstate`):

```bash
just infra my-cluster-name
```

3. Get the kubeconfig:

```bash
just kubeconfig my-cluster-name   # by name
just kubeconfig                   # interactive selection from managed clusters
```

The infrastructure creates a resource group, VNet, subnet, NSG (with all inbound traffic allowed), and an AKS cluster with a system node pool and a configurable user node pool with public IPs.

### Deploy the Platform

Once `kubectl` points at your cluster:

```bash
just deploy
```

Or run everything end-to-end:

```bash
just demo my-cluster-name     # provisions infra, gets kubeconfig, deploys platform
```

This bootstraps ArgoCD, which then takes over and deploys everything else from Git. The full platform takes several minutes to come up as components start in dependency order.

### Tear Down

```bash
just destroy my-cluster-name  # destroy by name (async, returns immediately)
just destroy                  # interactive selection from managed clusters
```


### Access Points

After deployment, these services are accessible (via NodePort or LoadBalancer depending on your cluster):

| Service | Default Credentials |
|---------|-------------------|
| ArgoCD | `admin` / `adminadmin` |
| Forgejo | `stackable` / `stackable` |
| Airflow Webserver | `admin` / `admin` |
| Entropy Data | Keycloak SSO: `demo-admin` (superadmin) / `demo-user`, organization `myorga` |
| Trino | `admin` (no password, HTTPS) |
| NiFi | See sealed secret |

### Other Commands

```bash
just demo <name>         # End-to-end: infra + kubeconfig + deploy
just infra <name>        # Provision AKS cluster (state: tofu/<name>.tfstate)
just kubeconfig [name]   # Get kubeconfig (interactive selection if no name)
just destroy [name]      # Tear down cluster (async, interactive if no name)
just seal-secrets        # Re-seal plaintext secrets from secrets/ into platform/manifests/
just dbt-compile         # Compile the dbt project locally
just dbt-run             # Run dbt models locally (requires Trino access)
```

## Components

### Ecosystem Integrations

| Component | Description |
|-----------|-------------|
| **[Entropy Data](https://www.entropy-data.com/)** | Data product marketplace with data contracts, lineage and Trino asset sync (Community Edition, [Helm chart](https://github.com/entropy-data/entropy-data-helm)) |
| **[Apache Superset](https://superset.apache.org/)** | Data exploration and visualization |
| **[dbt Core](https://www.getdbt.com/)** | Data transformation framework (TPC-H models) |
| **[OpenLineage](https://openlineage.io/) (`dbt-ol`)** | Lineage events from dbt runs, sent to Entropy Data |
| **[Data Contract CLI](https://cli.datacontract.com/)** | Tests data contracts against Trino and publishes results to Entropy Data |
| **[Lakekeeper](https://lakekeeper.io/)** | Apache Iceberg REST catalog |
| **[GarageFS](https://garagehq.deuxfleurs.fr/)** | S3-compatible distributed object storage |
| **[ArgoCD](https://argo-cd.readthedocs.io/)** | GitOps continuous deployment |
| **[Forgejo](https://forgejo.org/)** | In-cluster Git server (mirrors this repo) |
| **[SealedSecrets](https://sealed-secrets.netlify.app/)** | Encrypted secrets in Git |

### Trino Catalogs

| Catalog | Connector | Metastore | Storage |
|---------|-----------|-----------|---------|
| `tpch` | TPC-H | Built-in | In-memory |
| `tpcds` | TPC-DS | Built-in | In-memory |
| `hive` | Hive | Hive Metastore (PostgreSQL) | HDFS |
| `hive-iceberg` | Iceberg | Hive Metastore (PostgreSQL) | HDFS |
| `lakekeeper-iceberg` | Iceberg (REST) | Lakekeeper | GarageFS (S3) |

### Data Products

Data products live as code in `dags/dataproducts/<data-product-id>/`: an ODPS file, one ODCS file per data contract, and optionally a dbt project.

| Data product | Contents |
|---|---|
| `tpch-source` | Source-aligned: the TPC-H tables in `tpch.tiny`, described by an ODCS contract |
| `tpch-core` | Source-aligned: dbt project with 8 cleaned staging views (`stg_*`) in `hive-iceberg.demo`, input port from `tpch-source` |
| `tpch-order-summary`, `tpch-supplier-performance`, `tpch-revenue-by-region`, `tpch-customer-lifetime-value`, `tpch-shipping-analysis`, `tpch-part-pricing-analysis` | Consumer-aligned: one dbt project and one mart table each in `hive-iceberg.demo`, input port from `tpch-core`, one output port and data contract each |

`dags/dataproduct_dags.py` generates one Airflow DAG per folder (`dataproduct_<id>`). DAGs are chained along the ODPS input ports with Airflow assets: `tpch-source` runs daily, `tpch-core` runs after it, and the six marts run after `tpch-core`. Each DAG:
1. Publishes the ODPS and ODCS files to Entropy Data
2. Runs `dbt-ol build` (if there is a dbt project); `dbt-ol` sends OpenLineage events to Entropy Data, linked to the data product
3. Runs `datacontract test` for each output port contract against Trino and publishes the results to Entropy Data

To add a data product, add a folder and push it to the in-cluster Forgejo. The [entropydata-dbt-demo-builder](https://github.com/entropy-data/entropydata-dbt-demo-builder) coding-agent plugin scaffolds and implements such folders.

### Entropy Data Setup

Entropy Data runs from the [entropy-data-helm](https://github.com/entropy-data/entropy-data-helm) chart with a dedicated pgvector PostgreSQL. Login goes through Keycloak (client `entropy-data`); `demo-admin` is superadmin. The `entropy-data-init` job (`platform/manifests/entropy-data-init/`) then sets everything up headless:

1. Logs in as `demo-admin` via Keycloak and creates the organization `myorga`, with SSO auto join so every Keycloak user becomes a member on first login
2. Creates an organization API key and stores it in the Secret `platform/entropy-data-api-key` (used by the Airflow executors)
3. Creates the team `analytics-engineering`
4. Creates the Trino integration (asset sync of `tpch` and `hive-iceberg`, daily) and triggers a first run via the API

## More Topics

### Making Changes

Since ArgoCD manages the cluster, all changes should be committed to Git:

1. Push changes to the in-cluster Forgejo repository (automatically mirrored from GitHub)
2. ArgoCD detects changes and syncs
3. Manual `kubectl apply` commands are reverted by ArgoCD's self-heal

To add a new component, see the patterns documented in [CLAUDE.md](CLAUDE.md).

### Portability

The platform was originally AKS-only because Airflow mounted a `ReadWriteMany` PVC (`azurefile`) to share dbt artifacts between executor pods. That volume has been removed — dbt artifacts now flow through GarageFS (S3) using a per-task upload callback and a merging finalize step. The demo no longer depends on an RWX storage class.

The OpenTofu configuration in `tofu/` still provisions AKS, but the Kubernetes manifests themselves are portable. Running on another cloud or on-prem cluster requires only swapping the infra provisioning.

## Directory Structure

```
infrastructure/                    # Bootstrap: deployed by stackablectl
├── stack.yaml                     # stackablectl entry point
├── project.yaml                   # ArgoCD AppProject
├── cluster-apps.yaml              # App-of-apps: watches platform/applications/
├── forgejo.yaml                   # Forgejo deployment (mirrors this repo)
├── sealed-secrets.yaml            # SealedSecrets controller
├── forgejo-manifests/             # Forgejo admin secret + configure job
└── sealed-secrets-manifests/      # SealedSecrets decryption key

platform/                          # Everything ArgoCD manages after bootstrap
├── applications/                  # ArgoCD Application definitions (one per component)
└── manifests/                     # Kubernetes manifests grouped by component
    ├── airflow/                   # AirflowCluster CRD
    ├── airflow-postgres/          # PostgreSQL for Airflow
    ├── trino/                     # TrinoCluster + TrinoCatalog CRDs
    ├── trino-init/                # SQL init job (Kustomize overlay)
    ├── garagefs-init/             # GarageFS layout/bucket/key provisioning
    ├── lakekeeper-init/           # Lakekeeper bootstrap + warehouse creation
    ├── entropy-data/              # pgvector PostgreSQL, NodePort, CA truststore, sealed DB secret
    ├── entropy-data-init/         # Org, SSO auto join, API key, team, Trino integration
    ├── superset/                  # Apache Superset deployment
    ├── superset-postgres/         # PostgreSQL for Superset
    └── ...                        # HDFS, Hive, Kafka, NiFi, ZooKeeper, etc.

secrets/                           # Plaintext secrets (source of truth for sealing)
└── manifests/
    └── <component>/
        └── <secret-name>.yaml

dags/                              # Airflow DAGs (git-synced into pods)
├── dataproduct_dags.py            # One DAG per data product: publish, dbt-ol build, datacontract test
└── dataproducts/
    ├── tpch-source/               # ODPS + ODCS
    ├── tpch-core/                 # ODPS + ODCS + dbt project (8 staging views)
    └── tpch-<mart>/               # 6 marts: ODPS + ODCS + dbt project (1 mart table each)

tofu/                              # OpenTofu infrastructure (AKS cluster)
├── main.tf                        # Resource group, VNet, NSG, AKS cluster + node pools
├── terraform.tfvars.template      # Template for variable values
└── <name>.tfstate                 # Per-cluster state files (gitignored)
```

## Secrets Management

Secrets follow a two-step flow:

1. Store plaintext secrets in `secrets/manifests/<component>/<name>.yaml`
2. Run `just seal-secrets` to encrypt them into `platform/manifests/<component>/sealed-<name>.yaml`

Never edit `sealed-*` files by hand. Some secrets (GarageFS credentials) are generated at runtime by init jobs.

