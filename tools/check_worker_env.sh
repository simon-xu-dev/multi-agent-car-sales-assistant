#!/bin/bash
# Check worker container environment and add HICLAW_TEAM_ID
echo "=== Current lead-intake env (filtered) ==="
docker exec hiclaw-worker-lead-intake env 2>&1 | grep -i "HICLAW\|TEAM" | head -20

echo ""
echo "=== Adding HICLAW_TEAM_ID to container proc env ==="
# The container process env can't be modified directly, but we can use nsenter
# However, a simpler approach is to modify the worker startup script

# Check how the worker is started
docker exec hiclaw-worker-lead-intake sh -c "cat /proc/1/cmdline 2>/dev/null | tr '\0' ' ' ; echo" 2>&1
