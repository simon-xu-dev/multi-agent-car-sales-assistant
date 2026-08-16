#!/bin/bash
# 深挖 intent-analyst 在 18:05-18:20 的处理过程
date "+%H:%M:%S"
echo "=== intent-analyst 处理轨迹（过滤噪音）==="
docker logs hiclaw-worker-intent-analyst 2>&1 | awk '/2026-08-16 10:0[5-9]/,/2026-08-16 10:2/' | grep -iv "mc cp\|Transferred\|KiB\|┌\|└\|│\|Total\|Duration\|_on_room_event" | tail -20 | cut -c1-230
echo ""
echo "=== 是否有错误 ==="
docker logs hiclaw-worker-intent-analyst 2>&1 | awk '/2026-08-16 10:0[5-9]/,/2026-08-16 10:2/' | grep -i "error\|fail\|timeout\|exception" | tail -5 | cut -c1-230
