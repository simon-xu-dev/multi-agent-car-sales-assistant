#!/bin/bash
# 检查 DEAL-2002 任务 06 执行状态
date "+%H:%M:%S"
echo "=== order-executor 最近活动 ==="
docker logs hiclaw-worker-order-executor --since 8m 2>&1 | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration" | tail -8 | cut -c1-220
echo ""
echo "=== 是否有新的超时 ==="
for w in order-executor customer-ops carsales-demo-leader; do
  n=$(docker logs hiclaw-worker-$w --since 15m 2>&1 | grep -c "MODEL_TIMEOUT")
  echo "$w MODEL_TIMEOUT: $n"
done
echo ""
echo "=== task 06 目录产物 ==="
docker exec hiclaw-worker-intent-analyst sh -c "mc ls hiclaw/hiclaw-storage/shared/tasks/first-car-finance-20260816-140500-06/ 2>&1"
echo ""
echo "=== 已完成的任务目录总览 ==="
docker exec hiclaw-worker-intent-analyst sh -c "mc ls hiclaw/hiclaw-storage/shared/tasks/ 2>&1 | grep first-car"
