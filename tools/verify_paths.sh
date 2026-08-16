#!/bin/bash
# Verify: check both MinIO paths
echo "=== TeamLeader path (teams/carsales-demo/shared/tasks/) ==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "mc ls --recursive hiclaw/hiclaw-storage/teams/carsales-demo/shared/tasks/ 2>&1 | head -10"

echo ""
echo "=== Worker path (shared/tasks/) ==="
docker exec hiclaw-worker-lead-intake sh -c "mc ls --recursive hiclaw/hiclaw-storage/shared/tasks/family-suv-deal-20260816-103000-01/ 2>&1"
