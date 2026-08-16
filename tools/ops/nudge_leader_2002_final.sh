#!/bin/bash
# 催促 Leader 完成 DEAL-2002 最后阶段
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

python3 > /tmp/nudge_2002_final.json << 'PYEOF'
import json
body = """@carsales-demo-leader: DEAL-2002 进度确认：任务 04（strategy-planner 金融方案）、05（negotiation-executor 谈判）、06（order-executor 订单处理与征信审批闭环，结果 pending_approval：库存预留 RES-9D5329、报价 ¥125,021.20、金融合同已生成）均已 TASK_COMPLETED，08（knowledge-miner）也已完成，产物在全局 shared/tasks/first-car-finance-20260816-140500-0X/ 各目录。只剩最后一个子任务：请派发 07 给 customer-ops（交车安排与满意度回访，依赖订单结果）。派发时记得 delegate_task 后紧跟发送任务消息。customer-ops 完成后，立即输出 DEAL-2002 完整销售闭环报告（重点包含金融方案、审批路径 L2 审批单状态、让利与成交价），并调用 complete_project 关闭项目。"""
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

docker cp /tmp/nudge_2002_final.json hiclaw-controller:/tmp/nudge_2002_final.json
TXN=$(date +%s)
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/nudge_2002_final.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/nudge2002final_$TXN'" | head -c 200
echo ""
