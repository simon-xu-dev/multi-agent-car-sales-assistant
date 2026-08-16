#!/bin/bash
# 检查 negotiation-executor 房间和 Team 房间最近的消息
TOKEN="<MATRIX_ADMIN_TOKEN>"

fetch_room() {
    local ROOM="$1"
    local LABEL="$2"
    echo "=== $LABEL ==="
    docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $TOKEN' 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/messages?dir=b&limit=6'" > /tmp/room_msgs.json 2>/dev/null
    python3 - << 'PYEOF'
import json
with open('/tmp/room_msgs.json') as f:
    d = json.load(f)
for e in reversed(d.get('chunk', [])):
    if e.get('type') == 'm.room.message':
        c = e.get('content', {})
        sender = e.get('sender', '').split(':')[0]
        ts = e.get('origin_server_ts', 0) // 1000
        import datetime
        t = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        print(f"[{t}] {sender}: {c.get('body','')[:150]}")
PYEOF
}

fetch_room "!qAyQ4PdI1pryREd0Vc:matrix-local.hiclaw.io:18080" "Worker: negotiation-executor room"
fetch_room "!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080" "Team: carsales-demo room"
