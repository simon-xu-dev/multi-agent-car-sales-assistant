import json
with open('/tmp/admin_sync.json') as f:
    d = json.load(f)
for sec in ['join', 'invite', 'leave']:
    rooms = d.get('rooms', {}).get(sec, {})
    for rid, info in rooms.items():
        name = ''
        try:
            for e in info['state']['events']:
                if e.get('type') == 'm.room.name':
                    name = e.get('content', {}).get('name', '')
        except Exception:
            pass
        print(sec, rid[:30], name)
