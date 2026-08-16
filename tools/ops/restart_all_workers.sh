#!/bin/bash
# Restart all workers to apply the HICLAW_TEAM_ID environment variable

WORKERS="lead-intake intent-analyst profile-builder strategy-planner negotiation-executor order-executor knowledge-miner customer-ops"

for worker in $WORKERS; do
    container="hiclaw-worker-$worker"
    echo "=== Restarting $container ==="
    docker restart "$container" 2>&1
    sleep 2
done

echo "=== All workers restarted ==="
echo ""
echo "=== Checking worker status ==="
docker ps --filter "name=hiclaw-worker" --format "table {{.Names}}\t{{.Status}}" 2>&1
