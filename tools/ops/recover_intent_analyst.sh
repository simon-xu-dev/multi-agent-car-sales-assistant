#!/bin/bash
# 恢复 intent-analyst 任务 03（NO_REPLY 空回合）：重启 + 重发（含小步执行要求）
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

echo "=== 1. 重启 intent-analyst ==="
docker restart hiclaw-worker-intent-analyst
sleep 15

echo "=== 2. 重发任务消息 ==="
python3 > /tmp/redispatch_ia_body.json << 'PYEOF'
import json
body = """@intent-analyst 请重新执行任务 [trade-in-renewal-20260816-162000-03]：购买意图与置换需求分析。你上一轮执行结束时没有产出任何结果（空回合），已重启你的容器。这次请务必完成全部步骤：1) filesync pull 拉取 shared/tasks/trade-in-renewal-20260816-162000-03/spec.md；2) 分段小步执行，每条消息不超过 200 字；3) 把分析结果写入 shared/tasks/trade-in-renewal-20260816-162000-03/result.md 并 filesync push；4) 最后必须在房间里回复一行以 TASK_COMPLETED 开头的完成报告。不允许静默结束。"""
formatted = '<a href="https://matrix.to/#/@intent-analyst:matrix-local.hiclaw.io:18080">@intent-analyst</a> ' + body.split('@intent-analyst ', 1)[1].replace('\n', '<br/>')
content = {
    "msgtype": "m.text",
    "body": body,
    "format": "org.matrix.custom.html",
    "formatted_body": formatted,
    "m.mentions": {"user_ids": ["@intent-analyst:matrix-local.hiclaw.io:18080"]}
}
print(json.dumps(content, ensure_ascii=False))
PYEOF

docker cp /tmp/redispatch_ia_body.json hiclaw-controller:/tmp/redispatch_ia_body.json
TXN=$(date +%s)
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/redispatch_ia_body.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/redispatch_ia_$TXN'" | head -c 200
echo ""
echo "=== 完成 ==="
