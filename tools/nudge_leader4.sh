#!/bin/bash
# 纠正 Leader：delegate_task 之后必须发送实际的任务消息
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

python3 > /tmp/nudge4_body.json << 'PYEOF'
import json
body = """@carsales-demo-leader: 注意：你上次调用 taskflow delegate_task 后就结束了回合，但没有向 negotiation-executor 发送实际的任务消息，导致它 5 个小时没有收到任务。taskflow 只记录任务状态，派发任务还必须在 Team 房间里发送任务消息。请现在就补发，格式参考你之前给 lead-intake 派发的消息，例如：

negotiation-executor New task [family-suv-deal-20260816-094000-05]: 试驾预约与沟通谈判推进。请先执行 filesync pull 拉取 shared/tasks/family-suv-deal-20260816-094000-05/spec.md 并阅读，上游产物在 shared/tasks/ 对应目录下。完成后把结果写入 shared/tasks/family-suv-deal-20260816-094000-05/result.md 并 filesync push，然后 @carsales-demo-leader 告知结果。

补发后请记住这个流程：以后每次 delegate_task 之后，都必须紧接着在 Team 房间发送对应的任务消息给承接 Worker，两步都完成才算派发成功。后续节点（order-executor、customer-ops）也要同样处理，直到输出 DEAL-2001 完整闭环报告。"""
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

docker cp /tmp/nudge4_body.json hiclaw-controller:/tmp/nudge4_body.json
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -X PUT -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d @/tmp/nudge4_body.json 'http://127.0.0.1:6167/_matrix/client/v3/rooms/$ROOM/send/m.room.message/nudge_leader_txn_4'"
