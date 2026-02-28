#!/usr/bin/env bash
set -euo pipefail
BASE_URL=${BASE_URL:-http://localhost:3000}
MASTER_ID=${MASTER_ID:-2}
REQUEST_ID=${1:-2}

curl -s -o /tmp/race1.out -w "req1 status=%{http_code}\n" -X POST \
  -H "Accept: application/json" -H "Cookie: userId=${MASTER_ID}" \
  "$BASE_URL/master/requests/$REQUEST_ID/take" &
PID1=$!

curl -s -o /tmp/race2.out -w "req2 status=%{http_code}\n" -X POST \
  -H "Accept: application/json" -H "Cookie: userId=${MASTER_ID}" \
  "$BASE_URL/master/requests/$REQUEST_ID/take" &
PID2=$!

wait $PID1
wait $PID2

echo "--- req1 ---"; cat /tmp/race1.out; echo
echo "--- req2 ---"; cat /tmp/race2.out; echo
