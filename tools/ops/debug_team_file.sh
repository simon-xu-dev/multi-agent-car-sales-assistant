#!/bin/bash
docker exec hiclaw-worker-lead-intake python3 << 'PYEOF'
from pathlib import Path
print('HOME:', Path.home())
team_file = Path.home() / 'hiclaw-fs' / 'team_id'
print('team_file:', team_file)
print('exists:', team_file.exists())
if team_file.exists():
    print('content:', repr(team_file.read_text()))
PYEOF
