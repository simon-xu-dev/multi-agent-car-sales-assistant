#!/bin/bash
# 验证 team_id 修复是否还在
echo "=== 检查 lead-intake 的 team_id 修复 ==="
docker exec hiclaw-worker-lead-intake sh -c "cat /root/hiclaw-fs/team_id 2>&1"
echo ""
echo "=== 检查 sync.py 补丁 ==="
docker exec hiclaw-worker-lead-intake sh -c "grep -A 3 'Fallback 2' /opt/venv/copaw/lib/python3.11/site-packages/copaw_worker/sync.py 2>&1"
