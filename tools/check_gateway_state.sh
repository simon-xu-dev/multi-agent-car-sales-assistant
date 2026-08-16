#!/bin/bash
OUT=/Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/docs/RUN_EVIDENCE
echo "=== 网关进程启动参数 ==="
ps aux | grep "mock_tool_server" | grep -v grep | head -2
echo ""
echo "=== 查找持久化 trace 文件 ==="
ls -la /Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/tools/*.jsonl 2>/dev/null
ls -la /tmp/*trace* 2>/dev/null | head -5
find /Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow -name "*.jsonl" -newer /Users/chery-not-23982/Learn/competation/Agent-infra/SalesFlow/README.md 2>/dev/null | head -5
echo ""
echo "=== 网关端点探测 ==="
curl -s -m 5 "http://127.0.0.1:18089/tools/family_suv_deal/metrics" | head -c 300
echo ""
curl -s -m 5 "http://127.0.0.1:18089/tools/family_suv_deal/logs" | head -c 300
