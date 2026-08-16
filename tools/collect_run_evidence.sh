#!/bin/bash
# 采集今日（2026-08-16）三场景真实运行证据
# 1) Team 房间完整 transcript（分页拉取） 2) 三场景最终报告 3) 容器清单 4) MinIO 任务产物清单
OUT=/Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/docs/RUN_EVIDENCE
TOKEN="<MATRIX_ADMIN_TOKEN>"
ROOM="!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"

fetch() {
  docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer $TOKEN' '$1'"
}

echo "=== 1. 分页拉取 Team 房间全部消息 ==="
cat > /tmp/fetch_transcript.py << 'PYEOF'
import json, subprocess, urllib.parse, os

TOKEN = "<MATRIX_ADMIN_TOKEN>"
ROOM = "!RSGVna8h8WsCaAlamW:matrix-local.hiclaw.io:18080"
BASE = "http://127.0.0.1:6167/_matrix/client/v3"

def curl(url):
    cmd = ["docker", "exec", "hiclaw-controller", "sh", "-c",
           "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -s -H 'Authorization: Bearer " + TOKEN + "' '" + url + "'"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}

events = []
end = None
for page in range(40):
    url = f"{BASE}/rooms/{urllib.parse.quote(ROOM)}/messages?dir=b&limit=100"
    if end:
        url += "&from=" + urllib.parse.quote(end)
    d = curl(url)
    chunk = d.get("chunk", [])
    if not chunk:
        break
    events.extend(chunk)
    end = d.get("end")
    if not end or len(chunk) < 100:
        break

events.sort(key=lambda e: e.get("origin_server_ts", 0))
msgs = [e for e in events if e.get("type") == "m.room.message"]
print(f"TOTAL_EVENTS={len(events)} MESSAGES={len(msgs)}")
with open(os.environ["OUT"] + "/agentteams_20260816_transcript.json", "w") as f:
    json.dump(events, f, ensure_ascii=False)

# 提取三个最终报告
import datetime
reports = {}
for e in msgs:
    body = e.get("content", {}).get("body", "")
    sender = e.get("sender", "").split(":")[0]
    ts = datetime.datetime.fromtimestamp(e["origin_server_ts"] // 1000).strftime("%Y-%m-%d %H:%M:%S")
    if sender == "@carsales-demo-leader" and "全流程已完成" in body and body.startswith("##"):
        for deal in ("DEAL-2001", "DEAL-2002", "DEAL-2003"):
            if deal in body:
                reports[deal] = {"time": ts, "report": body}

with open(os.environ["OUT"] + "/agentteams_20260816_final_reports.json", "w") as f:
    json.dump(reports, f, ensure_ascii=False, indent=2)
for k, v in reports.items():
    print(f"REPORT {k}: {v['time']} ({len(v['report'])} chars)")
PYEOF
OUT=$OUT python3 /tmp/fetch_transcript.py

echo ""
echo "=== 2. 容器清单 ==="
docker ps --filter "name=hiclaw" --format "{{.Names}}\t{{.Status}}\t{{.Image}}" > $OUT/agentteams_20260816_containers.txt
cat $OUT/agentteams_20260816_containers.txt

echo ""
echo "=== 3. MinIO 三项目任务产物清单 ==="
docker exec hiclaw-worker-lead-intake sh -c "mc ls --recursive hiclaw/hiclaw-storage/shared/tasks/ 2>&1" > $OUT/agentteams_20260816_task_artifacts.txt
wc -l $OUT/agentteams_20260816_task_artifacts.txt
