#!/bin/bash
# 检查 intent-analyst（任务 03）状态
date "+%H:%M:%S"
echo "=== intent-analyst 最近活动 ==="
docker logs hiclaw-worker-intent-analyst --since 12m 2>&1 | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration" | tail -10 | cut -c1-230
echo ""
echo "=== 是否超时 ==="
docker logs hiclaw-worker-intent-analyst --since 20m 2>&1 | grep -c "MODEL_TIMEOUT"
echo ""
echo "=== task 03 目录 ==="
docker exec hiclaw-worker-lead-intake sh -c "mc ls hiclaw/hiclaw-storage/shared/tasks/trade-in-renewal-20260816-162000-03/ 2>&1"
