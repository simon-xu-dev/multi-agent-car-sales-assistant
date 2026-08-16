#!/bin/bash
# 检查 admin 在 Matrix server 上的实际房间状态

# Admin 登录
ADMIN_TOKEN=$(docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X POST -H 'Content-Type: application/json' -d '{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"admin\"},\"password\":\"<MANAGER_PASSWORD>\"}' 'http://127.0.0.1:6167/_matrix/client/v3/login' 2>&1" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

echo "=== Admin joined_rooms ==="
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $ADMIN_TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/joined_rooms' 2>&1" | python3 -m json.tool 2>/dev/null

echo ""
echo "=== Admin filter=joined_rooms (sync API) ==="
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $ADMIN_TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/sync?filter={\"room\":{\"timeline\":{\"limit\":0}}}&timeout=0' 2>&1" | python3 -c "
import sys, json
data = json.load(sys.stdin)
rooms = data.get('rooms', {}).get('join', {})
for room_id in rooms:
    print(room_id)
" 2>/dev/null
