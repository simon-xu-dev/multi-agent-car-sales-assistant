#!/bin/bash
# Check MinIO paths for TeamLeader and worker
echo "=== TeamLeader shared remote ==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "mc ls hiclaw/hiclaw-storage/shared/tasks/ 2>&1 | head -5"
echo ""
echo "=== TeamLeader teams remote ==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "mc ls hiclaw/hiclaw-storage/teams/ 2>&1 | head -5"
echo ""
echo "=== lead-intake shared remote ==="
docker exec hiclaw-worker-lead-intake sh -c "mc ls hiclaw/hiclaw-storage/shared/tasks/ 2>&1 | head -5"
echo ""
echo "=== lead-intake teams remote ==="
docker exec hiclaw-worker-lead-intake sh -c "mc ls hiclaw/hiclaw-storage/teams/ 2>&1 | head -5"
