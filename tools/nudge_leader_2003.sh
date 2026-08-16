#!/bin/bash
# 催促 Leader 继续 DEAL-2003 流程
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

python3 > /tmp/nudge_2003_body.json << 'PYEOF'
import json
body = """@carsales-demo-leader: DEAL-2003（trade_in_renewal 老客置换升级）流程请继续推进。lead-intake 已于 17:51 完成任务 trade-in-renewal-20260816-162000-01（老客户线索整建，产物已 filesync push 到全局 shared/tasks/trade-in-renewal-20260816-162000-01/）。请按 DAG 计划继续派发后续子任务（profile-builder、intent-analyst 可并行，knowledge-miner、strategy-planner、negotiation-executor、order-executor、customer-ops 按依赖顺序）。提醒：每次 delegate_task 后必须紧跟发送任务消息；每收到 worker 完成就立即派发下一个，中途不要停，直到输出 DEAL-2003 完整销售闭环报告并 complete_project。本场景重点：置换评估与升级方案、老客让利授权边界。"""
formatted = '<a href="https://matrix.to/#/@carsales-demo-leader:matrix-local.hiclaw.io:18080">@carsales-demo-leader</a>: ' + body.replace('@carsales-demo-leader: ', '').replace('\n', '<br/>')
content = {
    "msgtype": "m.text",
    "body": body,
    "format": "org.matrix.custom.html",
    "formatted_body": formatted,
    "m.mentions": {"user_ids": ["@carsales-demo-leader:matrix-local.hiclaw.io:18080"]}
}
print(json.dumps(content, ensure_ascii=False))
PYEOF

docker cp /tmp/nudge_2003_body.json hiclaw-controller:/tmp/nudge_2003_body.json
TXN=$(date +%s)
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/nudge_2003_body.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/nudge2003_$TXN'" | head -c 200
echo ""
