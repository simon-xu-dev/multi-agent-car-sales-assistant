#!/bin/bash
# 应用 mention 过滤补丁到 Leader（可重复执行）
LEADER=hiclaw-worker-carsales-demo-leader

echo "=== 1. 拷贝补丁并应用 ==="
docker cp /Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/tools/ops/patch_mention_filter.py $LEADER:/tmp/patch_mention_filter.py
docker exec $LEADER python3 /tmp/patch_mention_filter.py

echo "=== 2. 验证补丁已写入方法体 ==="
docker exec $LEADER sh -c "grep -c 'TASK_COMPLETED' /opt/venv/copaw/lib/python3.11/site-packages/copaw/app/channels/matrix/channel.py"

echo "=== 3. 重启 Leader 使补丁生效 ==="
docker restart $LEADER
sleep 20

echo "=== 4. 重启后验证 ==="
docker ps --filter "name=$LEADER" --format "{{.Names}}: {{.Status}}"
docker logs $LEADER --since 1m 2>&1 | tail -3 | cut -c1-150
