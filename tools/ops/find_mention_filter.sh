#!/bin/bash
# 定位 copaw 的 mention 过滤逻辑
echo "=== 搜索 mention / filter 相关代码 ==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "grep -n 'mention\|at_me\|is_at\|addressed\|not for me\|ignore' /opt/venv/copaw/lib/python3.11/site-packages/copaw/app/channels/matrix/channel.py | head -30"
echo ""
echo "=== 搜索 _on_room_event 附近逻辑 ==="
docker exec hiclaw-worker-carsales-demo-leader sh -c "grep -n '_on_room_event\|def _should\|def _filter' /opt/venv/copaw/lib/python3.11/site-packages/copaw/app/channels/matrix/channel.py | head -20"
