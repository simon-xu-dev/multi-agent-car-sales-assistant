#!/usr/bin/env python3
# 补丁：给 sync.py 的 _get_team_id 加 override 文件检查
# 如果 /root/hiclaw-fs/team_force_global 存在，强制返回 None（使用全局 shared/ 路径）
import sys

sync_file = '/opt/venv/copaw/lib/python3.11/site-packages/copaw_worker/sync.py'
with open(sync_file, 'r') as f:
    content = f.read()

if 'team_force_global' in content:
    print('already patched')
    sys.exit(0)

old = '''    def _get_team_id(self) -> Optional[str]:
        """Resolve the temporary runtime/storage team name from worker metadata."""
        worker = self._get_worker_info()'''

new = '''    def _get_team_id(self) -> Optional[str]:
        """Resolve the temporary runtime/storage team name from worker metadata."""
        import os as _os
        if _os.path.exists("/root/hiclaw-fs/team_force_global"):
            return None
        worker = self._get_worker_info()'''

if old not in content:
    print('ERROR: pattern not found')
    sys.exit(1)

content = content.replace(old, new)
with open(sync_file, 'w') as f:
    f.write(content)
print('patched OK')
