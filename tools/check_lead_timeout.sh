#!/bin/bash
# 检查 lead-intake 超时时间和模型配置
date "+%H:%M:%S"
echo "=== lead-intake MODEL_TIMEOUT 出现时间点 ==="
docker logs hiclaw-worker-lead-intake 2>&1 | grep -B2 "MODEL_TIMEOUT" | grep "^\(INFO\|ERROR\|WARNING\)\|2026" | tail -5 | cut -c1-200
echo ""
echo "=== lead-intake 超时前的活动 ==="
docker logs hiclaw-worker-lead-intake 2>&1 | grep "Handle agent query\|CoPawAgent.reply" | tail -5 | cut -c1-200
echo ""
echo "=== 容器环境变量（模型相关）==="
docker exec hiclaw-worker-lead-intake sh -c "env | grep -i 'model\|timeout\|LLM\|API' | head -10"
