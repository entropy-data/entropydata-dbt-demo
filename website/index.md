# Stackable Data Platform Demo

Welcome. This cluster is running the full Stackable Data Platform demo — a
GitOps-managed data lakehouse with Entropy Data, Airflow, Trino, dbt, and
a handful of supporting components.

## Platform Deployment 

| Service | URL | Username | Password | Enabled                                                                                      |
| --- | --- | --- | --- |----------------------------------------------------------------------------------------------|
| **ArgoCD** | [https://{{ nodeport "argocd-server-nodeport" }}/auth/login](https://{{ nodeport "argocd-server-nodeport" }}/auth/login) | `demo-admin` / `demo-user` | *(see keycloak-demo-passwords secret)* | —                                                                                            |
| **Forgejo** | [http://{{ nodeport "forgejo-http-nodeport" }}/user/oauth2/Keycloak](http://{{ nodeport "forgejo-http-nodeport" }}/user/oauth2/Keycloak) | `demo-admin` / `demo-user` | *(see keycloak-demo-passwords secret)* | —                                                                                            |
| **Keycloak** | [http://{{ nodeport "keycloak-nodeport" }}/realms/stackable-demo/account/](http://{{ nodeport "keycloak-nodeport" }}/realms/stackable-demo/account/) | `demo-admin` / `demo-user` | *(see keycloak-demo-passwords secret)* | —                                                                                            |


## Stackable Components
| Service | URL | Username | Password | Enabled                                                                                      |
| --- | --- | --- | --- |----------------------------------------------------------------------------------------------|
| **Airflow** | [http://{{ nodeport "airflow-webserver" }}/login/keycloak](http://{{ nodeport "airflow-webserver" }}/login/keycloak) | `demo-admin` / `demo-user` | *(see keycloak-demo-passwords secret)* | {{ toggle "platform/manifests/airflow/airflow.yaml" "spec.clusterOperation.stopped" }}       |
| **Trino** | [https://{{ nodeport "trino-coordinator" }}/](https://{{ nodeport "trino-coordinator" }}/) | `demo-admin` / `demo-user` | *(see keycloak-demo-passwords secret)* | {{ toggle "platform/manifests/trino/trino.yaml" "spec.clusterOperation.stopped" }}           |
| **Superset** | [http://{{ nodeport "simple-superset-node" }}/login/keycloak/?next=/superset/welcome/](http://{{ nodeport "simple-superset-node" }}/login/keycloak/?next=/superset/welcome/) | `demo-admin` / `demo-user` | *(see keycloak-demo-passwords secret)* | {{ toggle "platform/manifests/superset/superset.yaml" "spec.clusterOperation.stopped" }}     |
| **OpenSearch** | [https://{{ nodeport "simple-opensearch" }}/](https://{{ nodeport "simple-opensearch" }}/) | — | — | {{ toggle "platform/manifests/opensearch/opensearch.yaml" "spec.clusterOperation.stopped" }} |
| **NiFi** | [https://{{ nodeport "nifi-node" }}/](https://{{ nodeport "nifi-node" }}/) | `demo-admin` / `demo-user` | *(see keycloak-demo-passwords secret)* | {{ toggle "platform/manifests/nifi/nifi.yaml" "spec.clusterOperation.stopped" }}             |
| **Kafka** | — | — | — | {{ toggle "platform/manifests/kafka/kafka.yaml" "spec.clusterOperation.stopped" }}           |
| **HDFS** namenode-0 | [http://{{ nodeport "listener-simple-hdfs-namenode-default-0" }}/](http://{{ nodeport "listener-simple-hdfs-namenode-default-0" }}/) | — | — | {{ toggle "platform/manifests/hdfs/hdfs.yaml" "spec.clusterOperation.stopped" }}             |
| **HDFS** namenode-1 | [http://{{ nodeport "listener-simple-hdfs-namenode-default-1" }}/](http://{{ nodeport "listener-simple-hdfs-namenode-default-1" }}/) | — | — | —                                                                                            |
| **HDFS** datanode-0 | [http://{{ nodeport "simple-hdfs-datanode-default-0-listener" }}/](http://{{ nodeport "simple-hdfs-datanode-default-0-listener" }}/) | — | — | —                                                                                            |

## External Componens
| Service                   | URL | Username | Password | Enabled                                                                                      |
|---------------------------| --- | --- | --- |----------------------------------------------------------------------------------------------|
| **Entropy Data**          | [http://{{ nodeport "entropy-data-nodeport" }}/myorga](http://{{ nodeport "entropy-data-nodeport" }}/myorga) | `demo-admin` / `demo-user` | *(see keycloak-demo-passwords secret)* | —                                                                                            |
| **LakeKeeper**            | [http://{{ nodeport "lakekeeper" }}/ui/](http://{{ nodeport "lakekeeper" }}/ui/) | — | — | —                                                                                            |

Most Stackable-managed services run with a self-signed certificate; accept
the browser warning on first visit.

## What to look at

1. In **Entropy Data**, open a mart data product such as *Order
   Summary*: its data contract, the data contract test results, and the
   lineage graph that `dbt-ol` sent while building it from *Core*. The Trino
   tables themselves show up as assets via the Trino integration.
2. In **Airflow**, run the `dataproduct_*` DAGs. Each one publishes a data
   product from `dags/dataproducts/` to Entropy Data, builds it with dbt, and
   tests its data contract.
3. In **ArgoCD**, watch the continuously-reconciled application tree.
4. In **Forgejo**, browse the in-cluster git mirror of this repository. Add a
   folder to `dags/dataproducts/` and a new data product appears in Airflow
   and Entropy Data.

## Want to go deeper?

<div class="cta">

Questions about the platform, a specific use case, or want a guided
walkthrough of how Stackable fits your environment? We'd love to talk.

<a class="btn" href="https://zeeg.me/stackable/meet-stackable-mlsj">Contact us</a>

</div>
