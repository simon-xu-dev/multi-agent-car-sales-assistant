#!/bin/bash
# 查看 mention 过滤的关键代码段
echo "=== _was_mentioned 方法体（862-898行）==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "sed -n '862,898p' /opt/venv/copaw/lib/python3.11/site-packages/copaw/app/channels/matrix/channel.py"
echo ""
echo "=== 过滤判断处（1350-1375行）==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "sed -n '1350,1375p' /opt/venv/copaw/lib/python3.11/site-packages/copaw/app/channels/matrix/channel.py"
