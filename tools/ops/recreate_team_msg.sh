#!/bin/bash
# 向 manager 发送重建 Team 的指令
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!hQsuxHIvSXIhFkJrf2:matrix-local.hiclaw.io:18080"

MSG='Please recreate the Team NOW: create Team "carsales-demo" with TeamLeader "carsales-demo-leader" exactly as defined in the create_agents_messages.md content I sent earlier. The 8 business Workers (lead-intake, intent-analyst, profile-builder, strategy-planner, negotiation-executor, order-executor, knowledge-miner, customer-ops) are already Running — do NOT recreate them, just add them as Team members. Execute the team creation tool call immediately.'

BODY=$(python3 -c "import json,sys; print(json.dumps({'msgtype':'m.text','body':sys.argv[1]}))" "$MSG")

docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d '$BODY' 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/recreate_team_txn_1'"
