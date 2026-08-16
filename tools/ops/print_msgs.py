import json, datetime
with open('/tmp/team_msgs.json') as f:
    d = json.load(f)
for e in reversed(d.get('chunk', [])):
    if e.get('type') == 'm.room.message':
        ts = datetime.datetime.fromtimestamp(e.get('origin_server_ts', 0) // 1000).strftime('%H:%M:%S')
        sender = e.get('sender', '').split(':')[0]
        print(f"[{ts}] {sender}: {e.get('content', {}).get('body', '')[:130]}")
