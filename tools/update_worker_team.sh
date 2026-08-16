#!/bin/bash
# Try to update worker team via YAML manifest
echo "=== Create worker update YAML ==="
cat > /tmp/update_worker_team.yaml << 'EOF'
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: lead-intake
spec:
  team: carsales-demo
EOF

echo "=== Apply update ==="
docker cp /tmp/update_worker_team.yaml hiclaw-worker-lead-intake:/tmp/update_worker_team.yaml
docker exec hiclaw-worker-lead-intake sh -c "hiclaw apply -f /tmp/update_worker_team.yaml 2>&1"

echo ""
echo "=== Verify ==="
docker exec hiclaw-worker-lead-intake sh -c "hiclaw get workers lead-intake -o json 2>&1" | python3 -m json.tool 2>/dev/null | grep -E "team|role|name"
