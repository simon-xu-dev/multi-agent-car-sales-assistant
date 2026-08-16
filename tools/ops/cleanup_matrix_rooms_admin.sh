#!/bin/bash
# 彻底清理 Matrix 房间 - 使用 admin 用户

# Admin 登录获取 token
ADMIN_TOKEN=$(docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X POST -H 'Content-Type: application/json' -d '{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"admin\"},\"password\":\"<MANAGER_PASSWORD>\"}' 'http://127.0.0.1:6167/_matrix/client/v3/login' 2>&1" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

echo "Admin token: ${ADMIN_TOKEN:0:20}..."
echo ""

# 获取 admin 加入的所有房间
echo "=== Admin 加入的房间 ==="
ROOMS=$(docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $ADMIN_TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/joined_rooms' 2>&1" | python3 -c "import sys, json; data=json.load(sys.stdin); print('\n'.join(data.get('joined_rooms', [])))" 2>/dev/null)

echo "$ROOMS"
echo ""

# 离开所有房间（保留 Admin Room）
ADMIN_ROOM="!OyTxbafKXg9fJPWN3b:matrix-local.hiclaw.io:18080"

echo "=== 离开所有房间 ==="
for room in $ROOMS; do
    if [ "$room" != "$ADMIN_ROOM" ] && [ -n "$room" ]; then
        echo "离开: $room"
        docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X POST -H 'Authorization: Bearer $ADMIN_TOKEN' -H 'Content-Type: application/json' -d '{}' 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$room/leave' 2>&1"
    fi
done

echo ""
echo "=== 清理完成 ==="
echo "请在 Element Web 中完全刷新页面（Ctrl+Shift+R 或 Cmd+Shift+R）"
