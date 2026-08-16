#!/bin/bash
# 恢复 lead-intake 超时卡死：重启容器 + 重新派发任务消息
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

echo "=== 1. 重启 lead-intake 容器 ==="
docker restart hiclaw-worker-lead-intake
sleep 15

echo "=== 2. 重新发送任务消息（带标准 mention）==="
python3 > /tmp/redispatch_body.json << 'PYEOF'
import json
body = """@lead-intake 请重新执行任务 [first-car-finance-20260816-140500-01]（上一次执行因 LLM 超时失败，已重启你的容器）。请执行 filesync pull 拉取 shared/tasks/first-car-finance-20260816-140500-01/spec.md 并阅读，按 spec 完成线索归并与线索报告，把结果写入 shared/tasks/first-car-finance-20260816-140500-01/result.md 并 filesync push，然后回复 TASK_COMPLETED。控制输出篇幅，分步小步执行，避免单次推理过长。"""
formatted = '<a href="https://matrix.to/#/@lead-intake:matrix-local.hiclaw.io:18080">@lead-intake</a> ' + body.split('@lead-intake ', 1)[1].replace('\n', '<br/>')
content = {
    "msgtype": "m.text",
    "body": body,
    "format": "org.matrix.custom.html",
    "formatted_body": formatted,
    "m.mentions": {"user_ids": ["@lead-intake:matrix-local.hiclaw.io:18080"]}
}
print(json.dumps(content, ensure_ascii=False))
PYEOF

docker cp /tmp/redispatch_body.json hiclaw-controller:/tmp/redispatch_body.json
TXN=$(date +%s)
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/redispatch_body.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/redispatch_$TXN'" | head -c 300
echo ""
echo "=== 完成 ==="
