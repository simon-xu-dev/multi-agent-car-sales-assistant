#!/bin/bash
# 用标准 Matrix mention 格式催促 Leader
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"
LEADER_ID="@carsales-demo-leader:matrix-local.hiclaw.io:18080"

python3 > /tmp/nudge_body.json << 'PYEOF'
import json
body = "@carsales-demo-leader: 继续推进 DEAL-2001 全流程，不要停。当前进度：lead-intake、intent-analyst、profile-builder、knowledge-miner 的子任务已全部 TASK_COMPLETED，产出文件在全局 shared/tasks/family-suv-deal-20260816-094000-01/ 路径下。请立即按原任务计划派发剩余子任务（strategy-planner 制定报价策略 → negotiation-executor 谈判让利 → order-executor 订单执行 → customer-ops 交车与满意度回访）。全部子任务完成后，输出完整的销售闭环报告。每收到一个 TASK_COMPLETED 就立即派发下一个子任务，直到整个流程闭环。"
formatted = '<a href="https://matrix.to/#/@carsales-demo-leader:matrix-local.hiclaw.io:18080">@carsales-demo-leader</a>: 继续推进 DEAL-2001 全流程，不要停。当前进度：lead-intake、intent-analyst、profile-builder、knowledge-miner 的子任务已全部 TASK_COMPLETED，产出文件在全局 shared/tasks/family-suv-deal-20260816-094000-01/ 路径下。请立即按原任务计划派发剩余子任务（strategy-planner 制定报价策略 → negotiation-executor 谈判让利 → order-executor 订单执行 → customer-ops 交车与满意度回访）。全部子任务完成后，输出完整的销售闭环报告。每收到一个 TASK_COMPLETED 就立即派发下一个子任务，直到整个流程闭环。'
content = {
    "msgtype": "m.text",
    "body": body,
    "format": "org.matrix.custom.html",
    "formatted_body": formatted,
    "m.mentions": {"user_ids": ["@carsales-demo-leader:matrix-local.hiclaw.io:18080"]}
}
print(json.dumps(content, ensure_ascii=False))
PYEOF

docker cp /tmp/nudge_body.json hiclaw-controller:/tmp/nudge_body.json
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/nudge_body.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/nudge_leader_txn_2'"
