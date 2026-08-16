#!/bin/bash
# Fix: Modify copaw-worker entrypoint to set HICLAW_TEAM_ID
# Then restart all workers

WORKERS="lead-intake intent-analyst profile-builder strategy-planner negotiation-executor order-executor knowledge-miner customer-ops"

for worker in $WORKERS; do
    container="hiclaw-worker-$worker"
    echo "=== Fixing $container ==="

    # Find the copaw-worker entrypoint script
    docker exec "$container" sh -c "
    # Find where copaw-worker is installed
    which copaw-worker 2>/dev/null || echo 'not found'
    " 2>&1

    # Create a wrapper that sets HICLAW_TEAM_ID
    docker exec "$container" sh -c "
    cat > /usr/local/bin/copaw-worker-wrapper.sh << 'WRAPPER'
#!/bin/bash
export HICLAW_TEAM_ID=carsales-demo
exec /opt/venv/copaw/bin/copaw-worker \"\$@\"
WRAPPER
    chmod +x /usr/local/bin/copaw-worker-wrapper.sh
    echo 'Wrapper created'
    " 2>&1

    echo ""
done

echo "=== Now we need to update container entrypoints to use the wrapper ==="
echo "This requires recreating containers with modified entrypoints"
