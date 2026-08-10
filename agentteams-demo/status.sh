#!/bin/zsh
# SalesFlow AgentTeams 运行状态速查
# 用法：./status.sh            （查一次）
#       watch -n 15 ./status.sh（每15秒刷新）
# 判读：Trace 时间在涨 或 有 Worker 最近2分钟在说话 = 在干活

echo "════ $(date '+%H:%M:%S') DEAL-2001 状态速查 ════"

# 1. 业务工具调用（最硬的证据：Agent 真的在查 CRM/库存/价格）
echo ""
echo "── ① 工具网关 Trace（最近 3 条，时间涨=在干活）──"
docker exec hiclaw-manager sh -c "curl -s http://172.18.0.4:18089/tools/family_suv_deal/tools/trace" 2>/dev/null | python3 -c "
import json,sys
try:
    rs=json.load(sys.stdin).get('result',[])
    print(f'   累计调用 {len(rs)} 次')
    for x in rs[-3:]:
        t=x['time'][11:19] if 'T' in x['time'] else x['time'][-8:]
        print(f\"   {t}  {x['tool']}\")
except Exception as e:
    print('   (网关暂不可达)')
"

# 2. 各 Worker 最近 2 分钟是否有消息输出（LLM 推理/工具调用/回话）
echo ""
echo "── ② Agent 活跃度（最近 2 分钟有输出的 = 正在工作）──"
for w in salesflow-demo-leader lead-intake profile-builder intent-analyst knowledge-miner strategy-planner negotiation-executor order-executor customer-ops; do
    n=$(docker logs --since 2m "hiclaw-worker-$w" 2>&1 | grep -c "_on_room_event\|CoPawAgent.reply")
    if [ "$n" -gt 0 ]; then
        echo "   🟢 $w  ($n 条活动)"
    fi
done
echo "   （没列出的 = 最近 2 分钟空闲，可能在等 LLM 或等上游）"

# 3. LLM 推理等待检查（Agent 大部分时间其实在等云端模型，CPU 低≠卡死）
echo ""
echo "── ③ 最近一次推理启动时间（超过 15 分钟没新动静才算卡）──"
docker logs --since 20m hiclaw-worker-salesflow-demo-leader 2>&1 | grep "CoPawAgent.reply" | tail -1 | grep -oE "2026-[0-9-]+ [0-9:]+" | sed 's/^/   Leader: /'

echo ""
echo "════ 判读口诀 ════"
echo "①Trace 在涨 → 铁证在干活"
echo "②有 🟢 → 有 Agent 在工作"
echo "③都空闲 + 右侧面板显示'执行中' → 在等 LLM，再等 5-10 分钟"
echo "④都空闲 + 面板 15 分钟无变化 → 真卡了，找助手诊断"
