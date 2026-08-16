#!/bin/bash
# 检查 DEAL-2003 任务 01 是否被 lead-intake 接收执行
date "+%H:%M:%S"
echo "=== lead-intake 最近 10 分钟活动 ==="
docker logs hiclaw-worker-lead-intake --since 10m 2>&1 | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration" | tail -10 | cut -c1-230
echo ""
echo "=== lead-intake 是否收到任务消息（事件） ==="
docker logs hiclaw-worker-lead-intake --since 10m 2>&1 | grep "_on_room_event" | grep -o "body=.\{0,80\}" | tail -5
echo ""
echo "=== task 01 目录 ==="
docker exec hiclaw-worker-intent-analyst sh -c "mc ls hiclaw/hiclaw-storage/shared/tasks/trade-in-renewal-20260816-162000-01/ 2>&1"
echo ""
echo "=== leader 派发后是否还有活动 ==="
docker logs hiclaw-worker-carsales-demo-leader --since 8m 2>&1 | grep "Handle agent query\|CoPawAgent.reply\|Saved session" | tail -4 | cut -c1-180
