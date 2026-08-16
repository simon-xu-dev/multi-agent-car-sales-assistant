#!/bin/bash
# Verify the fix after restart
echo "=== Verifying lead-intake team_id ==="
docker exec hiclaw-worker-lead-intake python3 -c "
import os, sys
sys.path.insert(0, '/opt/venv/copaw/lib/python3.11/site-packages')
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)
from copaw_worker.sync import FileSync
sync = FileSync(
    endpoint=os.environ['HICLAW_FS_ENDPOINT'],
    access_key=os.environ['HICLAW_FS_ACCESS_KEY'],
    secret_key=os.environ['HICLAW_FS_SECRET_KEY'],
    bucket=os.environ['HICLAW_FS_BUCKET'],
    worker_name=os.environ['HICLAW_WORKER_NAME'],
    worker_cr_name=os.environ.get('HICLAW_WORKER_CR_NAME'),
)
print('team_id:', sync._get_team_id())
print('shared_remote:', sync._get_shared_remote())
" 2>&1

echo ""
echo "=== Verifying TeamLeader team_id ==="
docker exec hiclaw-worker-carsales-demo-leader python3 -c "
import os, sys
sys.path.insert(0, '/opt/venv/copaw/lib/python3.11/site-packages')
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)
from copaw_worker.sync import FileSync
sync = FileSync(
    endpoint=os.environ['HICLAW_FS_ENDPOINT'],
    access_key=os.environ['HICLAW_FS_ACCESS_KEY'],
    secret_key=os.environ['HICLAW_FS_SECRET_KEY'],
    bucket=os.environ['HICLAW_FS_BUCKET'],
    worker_name=os.environ['HICLAW_WORKER_NAME'],
    worker_cr_name=os.environ.get('HICLAW_WORKER_CR_NAME'),
)
print('team_id:', sync._get_team_id())
print('shared_remote:', sync._get_shared_remote())
" 2>&1

echo ""
echo "=== Checking worker status ==="
docker ps --filter "name=hiclaw-worker" --format "table {{.Names}}\t{{.Status}}" 2>&1
