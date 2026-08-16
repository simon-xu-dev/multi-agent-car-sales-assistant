#!/bin/bash
# 检查 DEAL-2002 执行情况
date "+%H:%M:%S"
echo "=== lead-intake 最近活动 ==="
docker logs hiclaw-worker-lead-intake --since 8m 2>&1 | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration" | tail -10 | cut -c1-250
echo ""
echo "=== 各 worker 容器最近 3 分钟事件数（活跃度）==="
for w in lead-intake intent-analyst profile-builder knowledge-miner strategy-planner negotiation-executor order-executor customer-ops carsales-demo-leader; do
  cnt=$(docker logs hiclaw-worker-$w --since 3m 2>&1 | grep -c "_on_room_event\|execute_shell\|Handle agent query")
  echo "$w: $cnt"
done
echo ""
echo "=== DEAL-2002 任务目录 ==="
docker exec hiclaw-worker-lead-intake sh -c "mc ls hiclaw/hiclaw-storage/shared/tasks/ 2>&1 | grep first-car"
