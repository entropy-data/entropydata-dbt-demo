demo name branch="main":
    just infra {{name}}
    just kubeconfig {{name}}
    just deploy {{branch}}

deploy branch="main":
    stackablectl stack install forgejo --stack-file infrastructure/stack.yaml -n deployment --stack-parameters repoRevision={{branch}}

# Rewrite branch-pinned references (Forgejo targetRevisions in
# platform/applications/ and refs/heads/ URLs in infrastructure/stack.yaml)
# so the checked-out branch self-references. Version-pinned Helm targetRevisions
# (e.g. "1.12.1") are left alone — only [a-zA-Z]-prefixed values match.
retarget branch:
    #!/usr/bin/env bash
    set -euo pipefail
    # Full commit SHAs (e.g. the pinned entropy-data-helm chart) are left alone.
    sed -i -E '/targetRevision: "[0-9a-f]{40}"/!s|targetRevision: "[a-zA-Z][a-zA-Z0-9_/-]*"|targetRevision: "{{branch}}"|g' platform/applications/*.yaml
    sed -i -E 's|refs/heads/[a-zA-Z][a-zA-Z0-9_/-]*/infrastructure/|refs/heads/{{branch}}/infrastructure/|g' infrastructure/stack.yaml
    echo "Retargeted to {{branch}}. Review with 'git diff' and commit when happy."

seal-secrets:
    #!/usr/bin/env bash
    set -euo pipefail
    # Seal offline against the canonical cert checked into the repo.
    # We do NOT ask the live cluster for the public key: the sealed-secrets
    # controller auto-rotates whenever the key on disk is older than its
    # --key-renew-period (default 30d), so a live-cluster fetch produces
    # bytes tied to a per-instance, throwaway key.
    CANONICAL_KEY_FILE=infrastructure/sealed-secrets-manifests/sealed-secrets-key.yaml
    CERT_FILE=$(mktemp -t sealed-secrets-cert.XXXXXX.pem)
    trap "rm -f $CERT_FILE" EXIT
    python3 -c "import yaml; print(yaml.safe_load(open('$CANONICAL_KEY_FILE'))['stringData']['tls.crt'])" > "$CERT_FILE"
    # Components living under infrastructure/ instead of platform/manifests/.
    # Their consuming ArgoCD Application sources infrastructure/<component>/, so
    # sealed siblings must be co-located there (not in platform/manifests/).
    INFRA_COMPONENTS=("keycloak-manifests")
    # Process all yaml files
    find secrets -type f \( -name "*.yaml" -o -name "*.yml" \) | while read -r input_file; do
        component=$(basename "$(dirname "$input_file")")
        if printf '%s\n' "${INFRA_COMPONENTS[@]}" | grep -qx "$component"; then
            output_dir="infrastructure/$component"
        else
            output_dir="$(dirname "${input_file/secrets/platform}")"
        fi
        mkdir -p "$output_dir"
        output_filename="sealed-$(basename "$input_file")"
        output_file="$output_dir/$output_filename"
        if [ -f "$output_file" ]; then
            echo "Skipping (already exists): $output_file"
            continue
        fi
        echo "Processing: $input_file -> $output_file"
        kubeseal --cert "$CERT_FILE" --scope=cluster-wide --format=yaml < "$input_file" > "$output_file"
    done

build-landing-image:
    docker build -t oci.stackable.tech/sandbox/demo-landing:0.2.3-dev demo-landing
    docker push oci.stackable.tech/sandbox/demo-landing:0.2.3-dev

[private]
_select-cluster:
    #!/usr/bin/env bash
    cd tofu
    states=(*.tfstate)
    if [ ! -e "${states[0]}" ]; then
        echo "No state files found in tofu/" >&2
        exit 1
    fi
    declare -a cluster_names
    for sf in "${states[@]}"; do
        cluster_names+=("${sf%.tfstate}")
    done
    if command -v rofi &>/dev/null; then
        selection=$(printf '%s\n' "${cluster_names[@]}" | rofi -dmenu -p "Select cluster")
        if [ -z "$selection" ]; then
            echo "No cluster selected" >&2
            exit 1
        fi
        echo "$selection"
    else
        echo "Select a cluster:" >&2
        for i in "${!cluster_names[@]}"; do
            echo "  $((i+1))) ${cluster_names[$i]}" >&2
        done
        read -rp "Choice [1-${#cluster_names[@]}]: " choice </dev/tty >&2
        if [ -z "$choice" ] || [ "$choice" -lt 1 ] || [ "$choice" -gt "${#cluster_names[@]}" ] 2>/dev/null; then
            echo "Invalid selection" >&2
            exit 1
        fi
        echo "${cluster_names[$((choice-1))]}"
    fi

infra name:
    #!/usr/bin/env bash
    cd tofu
    tofu init -upgrade
    tofu apply -auto-approve -var="name={{name}}" -state="{{name}}.tfstate"

destroy name="":
    #!/usr/bin/env bash
    if [ -n "{{name}}" ]; then
        CLUSTER="{{name}}"
    else
        CLUSTER=$(just _select-cluster)
    fi
    cd tofu
    RG=$(tofu output -raw -state="${CLUSTER}.tfstate" resource_group_name)
    echo "Deleting resource group '$RG' (async)..."
    az group delete --name "$RG" --yes --no-wait
    echo "Cleaning up state file '${CLUSTER}.tfstate'..."
    rm -f "${CLUSTER}.tfstate" "${CLUSTER}.tfstate.backup"

kubeconfig name="":
    #!/usr/bin/env bash
    if [ -n "{{name}}" ]; then
        CLUSTER="{{name}}"
    else
        CLUSTER=$(just _select-cluster)
    fi
    cd tofu
    RG=$(tofu output -raw -state="${CLUSTER}.tfstate" resource_group_name)
    az aks get-credentials --resource-group "$RG" --name "${CLUSTER}" --overwrite-existing

# Compile/run the dbt project of one data product, e.g. `just dbt-run tpch-core`
dbt-compile dataproduct="tpch-core":
    #!/usr/bin/env bash
    cd dags/dataproducts/{{dataproduct}}
    dbt compile --profiles-dir .

dbt-run dataproduct="tpch-core":
    #!/usr/bin/env bash
    cd dags/dataproducts/{{dataproduct}}
    dbt run --profiles-dir .
