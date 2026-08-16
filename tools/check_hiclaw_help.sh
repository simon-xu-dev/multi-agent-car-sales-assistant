#!/bin/bash
# Check if hiclaw CLI supports updating workers
echo "=== hiclaw commands ==="
docker exec hiclaw-worker-lead-intake sh -c "hiclaw --help 2>&1" | head -20

echo ""
echo "=== hiclaw get workers ==="
docker exec hiclaw-worker-lead-intake sh -c "hiclaw get workers --help 2>&1" | head -10

echo ""
echo "=== hiclaw update workers ==="
docker exec hiclaw-worker-lead-intake sh -c "hiclaw update workers --help 2>&1" | head -10
