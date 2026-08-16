#!/bin/bash
# 恢复 strategy-planner：重启 + 重发任务（强制小步执行）
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

echo "=== 1. 重启 strategy-planner 容器 ==="
docker restart hiclaw-worker-strategy-planner
sleep 15

echo "=== 2. 重发任务消息（带 mention，要求分段小步执行）==="
python3 > /tmp/redispatch_sp_body.json << 'PYEOF'
import json
body = """@strategy-planner 请继续执行任务 [first-car-finance-20260816-140500-04]：金融方案与审批路径设计。你之前因单次推理输出过长连续超时 3 次，这次必须改变执行方式：1) 先 filesync pull 拉取 shared/tasks/first-car-finance-20260816-140500-04/spec.md；2) 严格分段执行——每次回复只做一个小步骤，每条消息不超过 200 字，分多次 write_file 逐段写 plan.md（每次只写一个章节，不超过 500 字）；3) 全部章节写完后把最终摘要写入 shared/tasks/first-car-finance-20260816-140500-04/result.md 并 filesync push；4) 最后回复 TASK_COMPLETED。禁止一次性生成长文档。"""
formatted = '<a href="https://matrix.to/#/@strategy-planner:matrix-local.hiclaw.io:18080">@strategy-planner</a> ' + body.split('@strategy-planner ', 1)[1].replace('\n', '<br/>')
content = {
    "msgtype": "m.text",
    "body": body,
    "format": "org.matrix.custom.html",
    "formatted_body": formatted,
    "m.mentions": {"user_ids": ["@strategy-planner:matrix-local.hiclaw.io:18080"]}
}
print(json.dumps(content, ensure_ascii=False))
PYEOF

docker cp /tmp/redispatch_sp_body.json hiclaw-controller:/tmp/redispatch_sp_body.json
TXN=$(date +%s)
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/redispatch_sp_body.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/redispatch_sp_$TXN'" | head -c 200
echo ""
echo "=== 完成 ==="
