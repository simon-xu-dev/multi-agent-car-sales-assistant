#!/bin/bash
# 清理所有 hiclaw 运行痕迹

echo "=== 1. 停止并删除所有 hiclaw-worker 容器 ==="
docker ps -a --filter "name=hiclaw-worker" --format "{{.Names}}" | xargs -r docker stop 2>/dev/null
docker ps -a --filter "name=hiclaw-worker" --format "{{.Names}}" | xargs -r docker rm -f 2>/dev/null

echo ""
echo "=== 2. 清理 MinIO 中的任务数据 ==="
# 删除 MinIO 中的 tasks 目录
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && mc rm --recursive --force hiclaw/hiclaw-storage/shared/tasks/ 2>&1 || true"
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && mc rm --recursive --force hiclaw/hiclaw-storage/teams/carsales-demo/shared/tasks/ 2>&1 || true"

echo ""
echo "=== 3. 清理 Matrix 房间（通过 manager） ==="
# Manager 会在重启时自动清理旧房间
echo "Manager 重启后会自动清理旧房间"

echo ""
echo "=== 4. 重启 manager（清理旧房间数据） ==="
docker restart hiclaw-manager 2>&1
sleep 5

echo ""
echo "=== 5. 验证清理结果 ==="
echo "Worker 容器:"
docker ps --filter "name=hiclaw-worker" --format "table {{.Names}}\t{{.Status}}" 2>&1

echo ""
echo "Manager 状态:"
docker ps --filter "name=hiclaw-manager" --format "table {{.Names}}\t{{.Status}}" 2>&1

echo ""
echo "=== 清理完成 ==="
echo "现在可以重新开始运行 AgentTeams 流程了"
