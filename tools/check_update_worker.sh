#!/bin/bash
echo "=== hiclaw update worker help ==="
docker exec hiclaw-worker-lead-intake sh -c "hiclaw update worker --help 2>&1"
