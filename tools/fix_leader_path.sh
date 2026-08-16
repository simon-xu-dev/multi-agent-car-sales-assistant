#!/bin/bash
# 修复 leader 的 MinIO 路径：打补丁强制使用全局 shared/ 路径，与 worker 对齐
set -x

LEADER=hiclaw-worker-carsales-demo-leader
SRC=/Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/tools/patch_force_global.py

echo "=== 1. 拷贝补丁脚本到 leader ==="
docker cp "$SRC" "$LEADER":/tmp/patch_force_global.py

echo "=== 2. 应用补丁 ==="
docker exec "$LEADER" python3 /tmp/patch_force_global.py

echo "=== 3. 创建 override 文件 ==="
docker exec "$LEADER" sh -c "touch /root/hiclaw-fs/team_force_global && ls -la /root/hiclaw-fs/team_force_global"

echo "=== 4. 验证补丁生效（新导入模块）==="
docker exec "$LEADER" env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY python3 -c "
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
"

echo "=== 5. 同步团队路径已有任务文件到全局路径 ==="
docker exec "$LEADER" sh -c "mc mirror --overwrite hiclaw/hiclaw-storage/teams/carsales-demo/shared/tasks/ hiclaw/hiclaw-storage/shared/tasks/ 2>&1 | tail -5"

echo "=== 6. 重启 leader 使补丁生效 ==="
docker restart "$LEADER"

echo "=== done ==="
