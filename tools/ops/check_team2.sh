#!/bin/bash
TOKEN="<MATRIX_ADMIN_TOKEN>"

echo "=== All workers ==="
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/directory/list/room/hiclaw-manager-default:matrix-local.hiclaw.io:18080' 2>&1"

echo ""
echo "=== Controller workers API ==="
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $TOKEN' 'http://127.0.0.1:8090/api/workers' 2>&1 | python3 -m json.tool 2>/dev/null | head -60"
