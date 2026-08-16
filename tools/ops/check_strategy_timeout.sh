#!/bin/bash
# 检查 strategy-planner 超时后的状态
date "+%H:%M:%S"
echo "=== strategy-planner MODEL_TIMEOUT 时间点 ==="
docker logs hiclaw-worker-strategy-planner 2>&1 | grep "MODEL_TIMEOUT\|Saved session" | tail -4 | cut -c1-180
echo ""
echo "=== task 04 目录产物 ==="
docker exec hiclaw-worker-intent-analyst sh -c "mc ls --recursive hiclaw/hiclaw-storage/shared/tasks/first-car-finance-20260816-140500-04/ 2>&1"
echo ""
echo "=== 全部 worker 是否有超时 ==="
for w in lead-intake intent-analyst profile-builder knowledge-miner strategy-planner negotiation-executor order-executor customer-ops carsales-demo-leader; do
  n=$(docker logs hiclaw-worker-$w --since 30m 2>&1 | grep -c "MODEL_TIMEOUT")
  echo "$w: $n"
done
echo ""
echo "=== leader 最近活动 ==="
docker logs hiclaw-worker-carsales-demo-leader --since 10m 2>&1 | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration" | tail -5 | cut -c1-200
