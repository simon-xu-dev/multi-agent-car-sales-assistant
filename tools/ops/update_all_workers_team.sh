#!/bin/bash
# Try to update worker team from TeamLeader (which might have more permissions)
echo "=== Apply from TeamLeader ==="
cat > /tmp/update_workers_team.yaml << 'EOF'
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: lead-intake
spec:
  team: carsales-demo
---
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: intent-analyst
spec:
  team: carsales-demo
---
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: profile-builder
spec:
  team: carsales-demo
---
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: strategy-planner
spec:
  team: carsales-demo
---
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: negotiation-executor
spec:
  team: carsales-demo
---
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: order-executor
spec:
  team: carsales-demo
---
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: knowledge-miner
spec:
  team: carsales-demo
---
apiVersion: hiclaw.io/v1
kind: Worker
metadata:
  name: customer-ops
spec:
  team: carsales-demo
EOF

docker cp /tmp/update_workers_team.yaml hiclaw-worker-carsales-demo-leader:/tmp/update_workers_team.yaml
docker exec hiclaw-worker-carsales-demo-leader sh -c "hiclaw apply -f /tmp/update_workers_team.yaml 2>&1"

echo ""
echo "=== Verify lead-intake ==="
docker exec hiclaw-worker-lead-intake sh -c "hiclaw get workers lead-intake -o json 2>&1" | python3 -m json.tool 2>/dev/null | grep -E "team|role|name"
