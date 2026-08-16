#!/bin/bash
# Simpler fix: Create a team_id file in all workers and modify sync.py to read it

WORKERS="lead-intake intent-analyst profile-builder strategy-planner negotiation-executor order-executor knowledge-miner customer-ops carsales-demo-leader"

for worker in $WORKERS; do
    container="hiclaw-worker-$worker"
    echo "=== Fixing $container ==="

    # Create team_id file
    docker exec "$container" sh -c "echo 'carsales-demo' > /root/hiclaw-fs/team_id 2>&1"

    # Patch sync.py to read from file
    docker exec "$container" sh -c "
    python3 << 'PYEOF'
sync_file = '/opt/venv/copaw/lib/python3.11/site-packages/copaw_worker/sync.py'
with open(sync_file, 'r') as f:
    content = f.read()

# Find and replace the _get_team_id method
import re
pattern = r'    def _get_team_id\(self\) -> Optional\[str\]:.*?return _team_storage_name_from_worker_team\(self\.bucket, team_ref\)'

new_method = '''    def _get_team_id(self) -> Optional[str]:
        \"\"\"Resolve the temporary runtime/storage team name from worker metadata.\"\"\"
        worker = self._get_worker_info()
        team_ref = worker.get(\"team\")
        if not isinstance(team_ref, str) or not team_ref.strip():
            # Fallback 1: environment variable
            team_ref = os.environ.get(\"HICLAW_TEAM_ID\", \"\").strip()
        if not isinstance(team_ref, str) or not team_ref.strip():
            # Fallback 2: team_id file
            team_file = Path.home() / \"hiclaw-fs\" / \"team_id\"
            if team_file.exists():
                team_ref = team_file.read_text().strip()
        if not isinstance(team_ref, str) or not team_ref.strip():
            return None
        return _team_storage_name_from_worker_team(self.bucket, team_ref)'''

content = re.sub(pattern, new_method, content, flags=re.DOTALL)
with open(sync_file, 'w') as f:
    f.write(content)
print('SUCCESS')
PYEOF
    " 2>&1

    echo ""
done

echo "=== All workers fixed ==="
echo "=== Restarting all workers ==="
for worker in $WORKERS; do
    container="hiclaw-worker-$worker"
    docker restart "$container" 2>&1
    sleep 1
done

echo "=== Done ==="
