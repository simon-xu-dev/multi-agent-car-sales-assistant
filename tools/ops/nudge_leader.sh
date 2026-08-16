#!/bin/bash
# 催促 Leader 继续按任务计划派发后续子任务
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

MSG='@carsales-demo-leader 继续推进 DEAL-2001 全流程，不要停。当前进度：lead-intake、intent-analyst、profile-builder、knowledge-miner 的子任务已全部 TASK_COMPLETED，产出文件在全局 shared/tasks/family-suv-deal-20260816-094000-01/ 路径下。请立即按原任务计划派发剩余子任务（strategy-planner 制定报价策略 → negotiation-executor 谈判让利 → order-executor 订单执行 → customer-ops 交车与满意度回访），所有前置结果均可从 shared/ 全局路径拉取。全部子任务完成后，输出完整的销售闭环报告。全程自主推进，每收到一个 TASK_COMPLETED 就立即派发下一个子任务，直到整个流程闭环，不要中途停止。'

BODY=$(python3 -c "import json,sys; print(json.dumps({'msgtype':'m.text','body':sys.argv[1]}))" "$MSG")

docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d '$BODY' 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/nudge_leader_txn_1'"
