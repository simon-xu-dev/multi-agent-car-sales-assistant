#!/bin/bash
# 测试 lead-intake 和 leader 当前实际的 team_id 解析
echo "=== lead-intake ==="
docker exec hiclaw-worker-lead-intake env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY python3 -c "
import sys, os
sys.path.insert(0, '/opt/venv/copaw/lib/python3.11/site-packages')
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
" 2>&1 | tail -5
echo ""
echo "=== leader ==="
docker exec hiclaw-worker-carsales-demo-leader env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY python3 -c "
import sys, os
sys.path.insert(0, '/opt/venv/copaw/lib/python3.11/site-packages')
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
" 2>&1 | tail -5
