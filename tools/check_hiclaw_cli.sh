#!/bin/bash
echo "=== TeamLeader worker info ==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "hiclaw get workers carsales-demo-leader -o json 2>&1" | python3 -m json.tool 2>/dev/null | grep -E "team|role|name" | head -10

echo ""
echo "=== lead-intake worker info ==="
docker exec hiclaw-worker-lead-intake sh -c "hiclaw get workers lead-intake -o json 2>&1" | python3 -m json.tool 2>/dev/null | grep -E "team|role|name" | head -10
