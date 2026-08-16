#!/bin/bash
# 精确推进指令：列出已完成产物路径，要求派发剩余子任务
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

python3 > /tmp/nudge3_body.json << 'PYEOF'
import json
body = """@carsales-demo-leader: 请立即派发 DEAL-2001 的下一个子任务。已确认的全局 shared/tasks/ 产物（用 filesync pull shared/tasks/ 或 mc ls 验证）：
- family-suv-deal-20260816-094000-01/ result.md ✅ lead-intake 完成
- family-suv-deal-20260816-094000-02/ result.md ✅ profile-builder 完成
- family-suv-deal-20260816-094000-03/ result.md ✅ intent-analyst 完成
- family-suv-deal-20260816-094000-04/ sales-strategy.md ✅ strategy-planner 完成
- family-suv-deal-20260816-094000-08/ competitor-analysis.md ✅ knowledge-miner 完成
剩余待派发：negotiation-executor（谈判让利，依赖 04 的 sales-strategy.md）→ order-executor（订单执行）→ customer-ops（交车回访）→ 最终销售闭环报告。请现在就给 negotiation-executor 派发子任务，之后每收到 TASK_COMPLETED 立即派发下一个，直到输出闭环报告，不要停止。"""
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

docker cp /tmp/nudge3_body.json hiclaw-controller:/tmp/nudge3_body.json
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/nudge3_body.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/nudge_leader_txn_3'"
