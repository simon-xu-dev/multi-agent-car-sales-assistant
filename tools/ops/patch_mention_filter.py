#!/usr/bin/env python3
"""补丁：让任务协议消息（TASK_COMPLETED 等）绕过 mention 过滤，修复 Worker 完成报告被静默忽略的问题"""
path = "/opt/venv/copaw/lib/python3.11/site-packages/copaw/app/channels/matrix/channel.py"
with open(path) as f:
    src = f.read()

old = '''    def _was_mentioned(self, event: Any, text: str) -> bool:
        if not self._user_id:
            return False
        # 1. Check m.mentions (structured mention from Matrix spec)'''

new = '''    def _was_mentioned(self, event: Any, text: str) -> bool:
        if not self._user_id:
            return False
        # 0. Protocol messages (TASK_COMPLETED/TASK_RECEIVED/TASK_FAILED) always pass
        # the mention filter, so task reports are never silently dropped.
        _proto_body = (getattr(event, "body", None) or "") if event is not None else ""
        if any(_k in _proto_body for _k in ("TASK_COMPLETED", "TASK_RECEIVED", "TASK_FAILED")):
            return True
        # 1. Check m.mentions (structured mention from Matrix spec)'''

if "Protocol messages (TASK_COMPLETED" in src:
    print("ALREADY_PATCHED")
elif old in src:
    src = src.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(src)
    print("PATCHED_OK")
else:
    print("PATTERN_NOT_FOUND")
