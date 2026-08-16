#!/bin/bash
# 清理 Matrix 房间

TOKEN="<MATRIX_ADMIN_TOKEN>"

echo "=== 获取所有房间 ==="
ROOMS=$(docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/joined_rooms' 2>&1" | python3 -c "import sys, json; data=json.load(sys.stdin); print('\n'.join(data.get('joined_rooms', [])))" 2>/dev/null)

echo "找到的房间:"
echo "$ROOMS"
echo ""

echo "=== 离开所有房间（除了 Admin Room） ==="
ADMIN_ROOM="!OyTxbafKXg9fJPWN3b:matrix-local.hiclaw.io:18080"

for room in $ROOMS; do
    if [ "$room" != "$ADMIN_ROOM" ] && [ -n "$room" ]; then
        echo "离开房间: $room"
        docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X POST -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d '{}' 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$room/leave' 2>&1"
        echo ""
    fi
done

echo "=== 清理完成 ==="
echo "请在 Element Web 中刷新页面"
