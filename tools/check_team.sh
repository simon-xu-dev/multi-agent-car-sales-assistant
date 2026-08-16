#!/bin/bash
# Check team_id for TeamLeader and a worker
echo "=== TeamLeader ==="
docker exec hiclaw-worker-carsales-demo-leader python3 -c "
import os, json, urllib.request
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)
url = os.environ['HICLAW_CONTROLLER_URL'] + '/api/workers/' + os.environ['HICLAW_WORKER_CR_NAME']
req = urllib.request.Request(url)
req.add_header('Authorization', 'Bearer ' + os.environ['HICLAW_AUTH_TOKEN'])
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print('team:', data.get('team'))
print('role:', data.get('role'))
" 2>&1

echo "=== lead-intake worker ==="
docker exec hiclaw-worker-lead-intake python3 -c "
import os, json, urllib.request
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)
url = os.environ['HICLAW_CONTROLLER_URL'] + '/api/workers/' + os.environ['HICLAW_WORKER_CR_NAME']
req = urllib.request.Request(url)
req.add_header('Authorization', 'Bearer ' + os.environ['HICLAW_AUTH_TOKEN'])
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print('team:', data.get('team'))
print('role:', data.get('role'))
" 2>&1
