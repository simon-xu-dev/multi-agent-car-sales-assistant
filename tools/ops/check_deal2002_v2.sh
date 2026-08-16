#!/bin/bash
# 检查 DEAL-2002 恢复后 lead-intake 状态
date "+%H:%M:%S"
echo "=== task 01 目录内容 ==="
docker exec hiclaw-worker-intent-analyst sh -c "mc ls --recursive hiclaw/hiclaw-storage/shared/tasks/first-car-finance-20260816-140500-01/ 2>&1"
echo ""
echo "=== lead-intake 最近 3 分钟活动 ==="
docker logs hiclaw-worker-lead-intake --since 3m 2>&1 | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration" | tail -8 | cut -c1-230
