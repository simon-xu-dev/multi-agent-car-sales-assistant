#!/bin/bash
# 对所有 worker 应用 team_id 修复

echo "=== 等待所有 worker 启动完成 ==="
sleep 10

WORKERS=$(docker ps --filter "name=hiclaw-worker" --format "{{.Names}}" | grep -v leader)

for container in $WORKERS; do
    echo "=== 修复 $container ==="
    
    # 1. 创建 team_id 文件
    docker exec "$container" sh -c "echo 'carsales-demo' > /root/hiclaw-fs/team_id 2>&1"
    
    # 2. 补丁 sync.py
    docker exec "$container" sh -c "
    python3 << 'PYEOF'
sync_file = '/opt/venv/copaw/lib/python3.11/site-packages/copaw_worker/sync.py'
with open(sync_file, 'r') as f:
    content = f.read()

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

echo "=== 重启所有 worker 使修复生效 ==="
for container in $WORKERS; do
    docker restart "$container" 2>&1
    sleep 1
done

echo ""
echo "=== 验证修复 ==="
for container in $WORKERS; do
    echo "--- $container ---"
    docker exec "$container" sh -c "cat /root/hiclaw-fs/team_id 2>&1"
done

echo ""
echo "=== 修复完成 ==="
