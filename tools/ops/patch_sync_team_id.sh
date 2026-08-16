#!/bin/bash
# Fix: Add HICLAW_TEAM_ID fallback to _get_team_id in sync.py
# This fixes the path mismatch between TeamLeader and workers

docker exec hiclaw-worker-carsales-demo-leader sh -c "
python3 << 'PYEOF'
import re

sync_file = '/opt/venv/copaw/lib/python3.11/site-packages/copaw_worker/sync.py'
with open(sync_file, 'r') as f:
    content = f.read()

# Find the _get_team_id method and add env var fallback
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
    print('SUCCESS: _get_team_id patched with HICLAW_TEAM_ID fallback')
else:
    print('ERROR: Could not find _get_team_id method to patch')
    # Print the actual method for debugging
    import re
    match = re.search(r'def _get_team_id.*?(?=\n    def |\nclass |\Z)', content, re.DOTALL)
    if match:
        print('Found method:')
        print(match.group())
PYEOF
" 2>&1
