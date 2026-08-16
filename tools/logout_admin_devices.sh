#!/bin/bash
# 彻底清理：注销 admin 的 Matrix 设备，强制清除 Element Web 缓存

ADMIN_TOKEN=$(docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X POST -H 'Content-Type: application/json' -d '{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"admin\"},\"password\":\"<MANAGER_PASSWORD>\"}' 'http://127.0.0.1:6167/_matrix/client/v3/login' 2>&1" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

echo "=== Admin 当前设备 ==="
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $ADMIN_TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/devices' 2>&1" | python3 -m json.tool 2>/dev/null

echo ""
echo "=== 注销所有设备 ==="
DEVICES=$(docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $ADMIN_TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/devices' 2>&1" | python3 -c "import sys, json; data=json.load(sys.stdin); [print(d['device_id']) for d in data.get('devices', [])]" 2>/dev/null)

for device in $DEVICES; do
    echo "注销设备: $device"
    docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X DELETE -H 'Authorization: Bearer $ADMIN_TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/devices/$device' 2>&1"
    echo ""
done

echo "=== 验证：重新登录 ==="
NEW_TOKEN=$(docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X POST -H 'Content-Type: application/json' -d '{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"admin\"},\"password\":\"<MANAGER_PASSWORD>\"}' 'http://127.0.0.1:6167/_matrix/client/v3/login' 2>&1" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

echo "新 token: ${NEW_TOKEN:0:20}..."

echo ""
echo "=== 新 session 的房间列表 ==="
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $NEW_TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/joined_rooms' 2>&1" | python3 -m json.tool 2>/dev/null

echo ""
echo "=== 完成 ==="
echo "请在 Element Web 中注销 admin 账号，然后重新登录"
