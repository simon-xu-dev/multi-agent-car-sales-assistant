#!/bin/bash
# 检查 admin 的房间状态（join/invite/leave）
TOKEN="<MATRIX_ADMIN_TOKEN>"
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/sync?timeout=0&filter=%7B%22room%22%3A%7B%22timeline%22%3A%7B%22limit%22%3A1%7D%7D%7D'" > /tmp/admin_sync.json 2>/dev/null
python3 /Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/tools/ops/parse_rooms.py
