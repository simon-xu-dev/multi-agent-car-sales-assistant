#!/bin/bash
# Verify the fix: check team_id for workers after restart
echo "=== lead-intake team_id after fix ==="
docker exec hiclaw-worker-lead-intake python3 -c "
import os, sys
sys.path.insert(0, '/opt/venv/copaw/lib/python3.11/site-packages')
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)
# Set the env var for this session
os.environ['HICLAW_TEAM_ID'] = 'carsales-demo'
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
echo "=== Check if HICLAW_TEAM_ID is in environment ==="
docker exec hiclaw-worker-lead-intake sh -c "env | grep HICLAW_TEAM_ID 2>&1"
