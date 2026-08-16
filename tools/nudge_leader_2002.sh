#!/bin/bash
# 催促 Leader 继续 DEAL-2002 流程
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

python3 > /tmp/nudge_2002_body.json << 'PYEOF'
import json
body = """@carsales-demo-leader: DEAL-2002（first_car_finance）流程请继续推进。lead-intake 已于 17:03 完成任务 first-car-finance-20260816-140500-01（TASK_COMPLETED，LEAD-2002 多渠道线索整合建档，客户 CUST-2002，评分8分 P1），产物在全局 shared/tasks/first-car-finance-20260816-140500-01/ 下。请按任务计划派发后续子任务：profile-builder（客户画像）和 intent-analyst（意向分析，含金融资质预检）可并行 → strategy-planner（金融方案与审批路径设计，重点）→ knowledge-miner（竞品/金融产品信息挖掘）→ negotiation-executor（谈判让利）→ order-executor（订单与金融合同执行）→ customer-ops（交车与回访）。每次 delegate_task 后必须紧接着在房间发送任务消息（两步派发），worker 完成后立即派发下一个，直到输出 DEAL-2002 完整销售闭环报告，中途不要停。"""
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

docker cp /tmp/nudge_2002_body.json hiclaw-controller:/tmp/nudge_2002_body.json
TXN=$(date +%s)
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/nudge_2002_body.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/nudge2002_$TXN'" | head -c 200
echo ""
