#!/bin/bash
# 检查 negotiation-executor 是否在工作，以及 leader 状态
date "+%H:%M:%S"
echo "=== negotiation-executor 最近活动（过滤 mc 噪音）==="
docker logs hiclaw-worker-negotiation-executor --since 10m 2>&1 | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration" | tail -15 | cut -c1-250
echo ""
echo "=== leader 最近活动 ==="
docker logs hiclaw-worker-carsales-demo-leader --since 10m 2>&1 | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration" | tail -8 | cut -c1-250
echo ""
echo "=== task 05 目录产物 ==="
docker exec hiclaw-worker-lead-intake sh -c "mc ls --recursive hiclaw/hiclaw-storage/shared/tasks/family-suv-deal-20260816-094000-05/ 2>&1"
