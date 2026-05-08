#!/usr/bin/env bash
# Provision a Lambda Labs GPU instance for Ponder.
# Usage: ./provision.sh [launch|terminate|status|types]
# Requires: LAMBDA_API_KEY, LAMBDA_SSH_KEY_NAME env vars.

set -euo pipefail

API="https://cloud.lambdalabs.com/api/v1"
AUTH="Authorization: Basic $(echo -n "${LAMBDA_API_KEY}:" | base64)"

INSTANCE_TYPE="${LAMBDA_INSTANCE_TYPE:-gpu_1x_a10}"
REGION="${LAMBDA_REGION:-us-west-2}"
SSH_KEY_NAME="${LAMBDA_SSH_KEY_NAME}"
INSTANCE_NAME="${LAMBDA_INSTANCE_NAME:-ponder-dev}"

cmd="${1:-status}"

case "$cmd" in
  launch)
    echo "Launching $INSTANCE_TYPE in $REGION ..."
    curl -sS -X POST "$API/instance-operations/launch" \
      -H "$AUTH" \
      -H "Content-Type: application/json" \
      -d "{
        \"region_name\": \"$REGION\",
        \"instance_type_name\": \"$INSTANCE_TYPE\",
        \"ssh_key_names\": [\"$SSH_KEY_NAME\"],
        \"name\": \"$INSTANCE_NAME\"
      }" | python3 -m json.tool
    ;;

  terminate)
    echo "Fetching running instances ..."
    INSTANCE_IDS=$(curl -sS "$API/instances" -H "$AUTH" \
      | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']
ids = [i['id'] for i in data if i.get('name') == '${INSTANCE_NAME}']
print(' '.join(ids))
")
    if [ -z "$INSTANCE_IDS" ]; then
      echo "No running instances named $INSTANCE_NAME found."
      exit 0
    fi
    echo "Terminating: $INSTANCE_IDS"
    IDS_JSON=$(python3 -c "import json,sys; ids='${INSTANCE_IDS}'.split(); print(json.dumps({'instance_ids': ids}))")
    curl -sS -X POST "$API/instance-operations/terminate" \
      -H "$AUTH" \
      -H "Content-Type: application/json" \
      -d "$IDS_JSON" | python3 -m json.tool
    ;;

  status)
    curl -sS "$API/instances" -H "$AUTH" \
      | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']
if not data:
    print('No running instances.')
else:
    for i in data:
        print(f\"{i['id']}  {i['name']}  {i['instance_type']['name']}  {i['status']}  {i.get('ip','-')}\")
"
    ;;

  types)
    curl -sS "$API/instance-types" -H "$AUTH" \
      | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']
for name, info in data.items():
    avail = info.get('regions_with_capacity_available', [])
    regions = [r['name'] for r in avail]
    gpu = info['instance_type'].get('gpu_description', '-')
    price = info['instance_type']['price_cents_per_hour']
    print(f'{name:<30} \${price/100:.2f}/hr  GPU:{gpu}  regions:{regions}')
"
    ;;

  ssh)
    IP=$(curl -sS "$API/instances" -H "$AUTH" \
      | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']
for i in data:
    if i.get('name') == '${INSTANCE_NAME}':
        print(i.get('ip', ''))
        break
")
    if [ -z "$IP" ]; then
      echo "No running instance named $INSTANCE_NAME found."
      exit 1
    fi
    echo "Connecting to $IP ..."
    ssh -o StrictHostKeyChecking=no ubuntu@"$IP"
    ;;

  *)
    echo "Usage: $0 [launch|terminate|status|types|ssh]"
    exit 1
    ;;
esac
