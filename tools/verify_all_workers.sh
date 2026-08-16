#!/bin/bash
# 验证所有 worker 的 team_id 修复和 mock 网关状态
for w in knowledge-miner customer-ops order-executor negotiation-executor profile-builder strategy-planner intent-analyst; do
    R=$(docker exec "hiclaw-worker-$w" sh -c "cat /root/hiclaw-fs/team_id 2>/dev/null; echo -n '|'; grep -c 'Fallback' /opt/venv/copaw/lib/python3.11/site-packages/copaw_worker/sync.py 2>/dev/null")
    echo "$w => $R"
done
echo "--- mock server health ---"
curl -s -m 3 http://127.0.0.1:18089/health || echo "MOCK SERVER NOT RUNNING"
