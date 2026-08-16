#!/bin/bash
# Fix all workers: patch sync.py and set HICLAW_TEAM_ID

WORKERS="lead-intake intent-analyst profile-builder strategy-planner negotiation-executor order-executor knowledge-miner customer-ops"

for worker in $WORKERS; do
    container="hiclaw-worker-$worker"
    echo "=== Patching $container ==="

    # Patch sync.py
    docker exec "$container" sh -c "
    python3 << 'PYEOF'
import re

sync_file = '/opt/venv/copaw/lib/python3.11/site-packages/copaw_worker/sync.py'
with open(sync_file, 'r') as f:
    content = f.read()

old_method = '''    def _get_team_id(self) -> Optional[str]:
        \"\"\"Resolve the temporary runtime/storage team name from worker metadata.\"\"\"
        worker = self._get_worker_info()
        team_ref = worker.get(\"team\")
        if not isinstance(team_ref, str) or not team_ref.strip():
            return None
        return _team_storage_name_from_worker_team(self.bucket, team_ref)'''

new_method = '''    def _get_team_id(self) -> Optional[str]:
        \"\"\"Resolve the temporary runtime/storage team name from worker metadata.\"\"\"
        worker = self._get_worker_info()
        team_ref = worker.get(\"team\")
        if not isinstance(team_ref, str) or not team_ref.strip():
            # Fallback to environment variable if controller doesn't return team field
            team_ref = os.environ.get(\"HICLAW_TEAM_ID\", \"\").strip()
        if not isinstance(team_ref, str) or not team_ref.strip():
            return None
        return _team_storage_name_from_worker_team(self.bucket, team_ref)'''

if old_method in content:
    content = content.replace(old_method, new_method)
    with open(sync_file, 'w') as f:
        f.write(content)
    print('SUCCESS: patched')
else:
    print('SKIP: already patched or method not found')
PYEOF
    " 2>&1

    # Set HICLAW_TEAM_ID environment variable
    echo "Setting HICLAW_TEAM_ID for $container..."
    docker exec "$container" sh -c "echo 'export HICLAW_TEAM_ID=carsales-demo' >> /root/.bashrc 2>/dev/null; echo 'HICLAW_TEAM_ID=carsales-demo' >> /etc/environment 2>/dev/null; echo 'done'" 2>&1

    echo ""
done

echo "=== All workers patched ==="
