#!/bin/bash
# 验证 leader 是否补发了任务消息、negotiation-executor 是否开始工作
echo "=== negotiation-executor recent ==="
docker logs hiclaw-worker-negotiation-executor --since 5m 2>&1 | grep -i "Handle agent query\|filesync\|spec.md" | head -3 | cut -c1-200

echo "=== team room latest 5 messages ==="
TOKEN="<MATRIX_ADMIN_TOKEN>"
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/rooms/!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080/messages?dir=b&limit=5'" > /tmp/team_msgs.json 2>/dev/null
python3 /Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/tools/print_msgs.py
