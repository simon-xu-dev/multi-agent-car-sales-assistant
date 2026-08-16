import { useState, useEffect } from 'react'
import { agents } from '../data/agents'
import teamSpec from '../data/team_spec.json'

// Agent 协同关系（基于 Skill 依赖图）
const COLLAB_EDGES = [
  { from: 'lead_intake', to: 'profile_builder', label: '线索→画像', skill: 'lead-fusion' },
  { from: 'profile_builder', to: 'intent_analyst', label: '画像→意图', skill: 'profile-building' },
  { from: 'intent_analyst', to: 'strategy_planner', label: '意图→策略', skill: 'intent-scoring' },
  { from: 'strategy_planner', to: 'negotiation_executor', label: '策略→议价', skill: 'car-recommendation' },
  { from: 'negotiation_executor', to: 'order_executor', label: '议价→订单', skill: 'quote-pricing' },
  { from: 'order_executor', to: 'knowledge_miner', label: '订单→沉淀', skill: 'case-mining' },
  { from: 'customer_ops', to: 'knowledge_miner', label: '运营→沉淀', skill: 'case-mining' },
]

// Agent 在管线中的激活步骤（对应 liveScripts.js 的 agent 字段）
const ACTIVATION_MAP = {
  lead_intake: [1, 2, 3, 7],
  profile_builder: [1, 2, 3],
  intent_analyst: [4, 5, 6],
  strategy_planner: [8, 9, 10, 11],
  negotiation_executor: [12, 13, 14, 15],
  order_executor: [16, 17],
  customer_ops: [],
  knowledge_miner: [],
}

const RISK_COLORS = {
  L0: { bg: 'bg-slate-600/30', border: 'border-slate-500/40', text: 'text-slate-300', glow: '' },
  L1: { bg: 'bg-green-500/15', border: 'border-green-500/40', text: 'text-green-400', glow: 'shadow-green-500/20' },
  L2: { bg: 'bg-yellow-500/15', border: 'border-yellow-500/40', text: 'text-yellow-400', glow: 'shadow-yellow-500/20' },
  L3: { bg: 'bg-red-500/15', border: 'border-red-500/40', text: 'text-red-400', glow: 'shadow-red-500/20' },
}

export default function AgentCollaboration({ activeAgents = [], activeStep = -1, currentRisk = '' }) {
  const [hoveredAgent, setHoveredAgent] = useState(null)
  const [showEdges, setShowEdges] = useState(true)

  const isActive = (agentId) => activeAgents.includes(agentId)
  const agentMap = Object.fromEntries(agents.map((a) => [a.id, a]))

  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <h2 className="text-3xl font-bold">Agent 协同拓扑</h2>
        <p className="text-slate-400 text-sm max-w-2xl mx-auto">
          8 个 Worker Agent + 1 个 TeamLeader 基于 AgentTeams 框架的实时协同可视化。
          活跃 Agent 高亮，数据流向动态展示。
        </p>
      </div>

      {/* 控制面板 */}
      <div className="flex items-center justify-center gap-4">
        <button
          onClick={() => setShowEdges(!showEdges)}
          className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
            showEdges ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'bg-slate-800 text-slate-400'
          }`}
        >
          {showEdges ? '◉ 协同关系' : '○ 协同关系'}
        </button>
        <div className="flex gap-2 text-xs">
          {Object.entries(RISK_COLORS).map(([level, cls]) => (
            <span key={level} className={`px-2 py-1 rounded ${cls.bg} ${cls.border} border ${cls.text}`}>
              {level}
            </span>
          ))}
        </div>
      </div>

      {/* TeamLeader */}
      <div className="flex justify-center">
        <div className={`relative px-6 py-4 rounded-xl border-2 transition-all duration-300 ${
          activeAgents.length > 0
            ? 'bg-purple-500/20 border-purple-500/60 shadow-lg shadow-purple-500/20'
            : 'bg-purple-500/10 border-purple-500/30'
        }`}>
          <div className="flex items-center gap-3">
            <span className="text-2xl">🎯</span>
            <div>
              <div className="font-bold text-purple-400">TeamLeader</div>
              <div className="text-xs text-slate-400">DAG 任务拆解 · 上下文传递 · 结果汇总</div>
            </div>
            {activeAgents.length > 0 && (
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-purple-400 rounded-full animate-pulse" />
            )}
          </div>
        </div>
      </div>

      {/* 连接线 */}
      <div className="flex justify-center">
        <div className={`w-0.5 h-8 transition-colors ${activeAgents.length > 0 ? 'bg-purple-500/50' : 'bg-slate-700'}`} />
      </div>

      {/* Agent 网格 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {agents.map((agent) => {
          const active = isActive(agent.id)
          const hovered = hoveredAgent === agent.id
          const step = teamSpec.workflow.find((w) => w.agent === agent.id)
          const riskCls = RISK_COLORS[active && currentRisk ? currentRisk : 'L0']

          return (
            <div
              key={agent.id}
              onMouseEnter={() => setHoveredAgent(agent.id)}
              onMouseLeave={() => setHoveredAgent(null)}
              className={`relative rounded-xl p-4 border transition-all duration-300 cursor-pointer ${
                active
                  ? `${riskCls.bg} ${riskCls.border} border-2 shadow-lg ${riskCls.glow}`
                  : 'bg-slate-800/30 border-slate-700/30 hover:border-slate-600/50'
              }`}
            >
              {/* 状态指示器 */}
              {active && (
                <span className={`absolute top-2 right-2 w-2.5 h-2.5 rounded-full animate-pulse ${
                  currentRisk === 'L2' ? 'bg-yellow-400' : currentRisk === 'L3' ? 'bg-red-400' : 'bg-green-400'
                }`} />
              )}

              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl">{agent.icon}</span>
                <div>
                  <div className={`text-sm font-semibold ${active ? riskCls.text : 'text-slate-300'}`}>
                    {agent.nameCn}
                  </div>
                  {step && (
                    <div className="text-xs text-slate-500">Step {step.step}</div>
                  )}
                </div>
              </div>

              {/* Skills */}
              <div className="flex gap-1 flex-wrap mt-2">
                {agent.skills.slice(0, 2).map((skill, idx) => (
                  <span key={idx} className={`px-1.5 py-0.5 rounded text-xs ${
                    active ? 'bg-purple-500/30 text-purple-300' : 'bg-slate-700/50 text-slate-500'
                  }`}>
                    {skill}
                  </span>
                ))}
              </div>

              {/* Hover 详情 */}
              {hovered && (
                <div className="absolute left-0 right-0 top-full mt-2 z-10 bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-xl">
                  <div className="text-xs text-slate-300 mb-1">{agent.role}</div>
                  <div className="text-xs text-slate-500">
                    工具: {agent.tools.join(', ')}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 协同关系连线说明 */}
      {showEdges && (
        <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-5">
          <h3 className="font-semibold mb-3 text-cyan-400 text-sm">协同数据流（Skill 依赖图）</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {COLLAB_EDGES.map((edge, idx) => {
              const fromAgent = agentMap[edge.from]
              const toAgent = agentMap[edge.to]
              const bothActive = isActive(edge.from) && isActive(edge.to)
              return (
                <div
                  key={idx}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors ${
                    bothActive ? 'bg-blue-500/15 border border-blue-500/30' : 'bg-slate-800/50'
                  }`}
                >
                  <span>{fromAgent?.icon}</span>
                  <span className={`flex-1 ${bothActive ? 'text-blue-300' : 'text-slate-400'}`}>
                    {edge.label}
                  </span>
                  <span className="text-slate-500">→</span>
                  <span>{toAgent?.icon}</span>
                  <span className={`px-1.5 py-0.5 rounded text-xs ${
                    bothActive ? 'bg-purple-500/30 text-purple-300' : 'bg-slate-700 text-slate-500'
                  }`}>
                    {edge.skill}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 当前步骤信息 */}
      {activeStep >= 0 && (
        <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-500/20 border border-blue-500/30 rounded-full flex items-center justify-center text-xs font-bold text-blue-400">
              {activeStep + 1}
            </div>
            <div className="flex-1">
              <div className="text-sm text-slate-300">
                当前活跃 Agent: {activeAgents.map((id) => agentMap[id]?.nameCn || id).join('、') || '—'}
              </div>
            </div>
            {currentRisk && (
              <span className={`px-2 py-1 rounded text-xs ${RISK_COLORS[currentRisk]?.bg} ${RISK_COLORS[currentRisk]?.text}`}>
                {currentRisk}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
