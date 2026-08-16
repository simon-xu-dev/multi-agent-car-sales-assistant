#!/bin/bash
# The error says to update via PUT /api/v1/teams/carsales-demo
# Let's check the team API

echo "=== Get team info ==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "hiclaw get teams carsales-demo -o json 2>&1" | python3 -m json.tool 2>/dev/null | head -30

echo ""
echo "=== hiclaw update team help ==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "hiclaw update team --help 2>&1"
