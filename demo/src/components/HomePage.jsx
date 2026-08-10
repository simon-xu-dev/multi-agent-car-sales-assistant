import { agents } from '../data/agents'

export default function HomePage({ onNavigate }) {
  const highlights = [
    {
      icon: '🤝',
      title: '多Agent协同',
      desc: '8个专业Agent分工协作，基于AgentTeams框架实现端到端自主成交闭环',
      color: 'from-blue-500 to-cyan-500',
    },
    {
      icon: '🛠️',
      title: 'Skill工程体系',
      desc: '可复用Skill能力抽象层，覆盖线索聚合、画像构建、意图识别、策略生成等核心能力',
      color: 'from-purple-500 to-pink-500',
    },
    {
      icon: '🔌',
      title: 'MCP工具网关',
      desc: '统一Mock工具网关，集成CRM、知识库、库存、价格、金融、试驾等外部系统',
      color: 'from-orange-500 to-red-500',
    },
    {
      icon: '📊',
      title: '可观测Trace',
      desc: '完整记录Agent推理轨迹与工具调用链路，支持全链路回放与审计',
      color: 'from-green-500 to-emerald-500',
    },
  ]

  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <div className="text-center space-y-6">
        <h1 className="text-5xl font-bold bg-gradient-to-r from-blue-400 via-cyan-400 to-teal-400 bg-clip-text text-transparent">
          CarSales
        </h1>
        <p className="text-xl text-slate-300 max-w-3xl mx-auto">
          基于多Agent协同的汽车销售自主成交智能助手
        </p>
        <p className="text-sm text-slate-400 max-w-2xl mx-auto">
          融合线索聚合、客户画像、意图识别、策略生成、智能议价、订单执行、客户运营、知识沉淀等8大Agent能力，
          实现从客户咨询到成交的全链路自主闭环
        </p>
      </div>

      {/* Highlights */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {highlights.map((item, idx) => (
          <div
            key={idx}
            className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6 hover:border-slate-600 transition-all"
          >
            <div className={`text-4xl mb-4 bg-gradient-to-r ${item.color} w-fit p-3 rounded-lg`}>
              {item.icon}
            </div>
            <h3 className="text-lg font-semibold mb-2">{item.title}</h3>
            <p className="text-sm text-slate-400">{item.desc}</p>
          </div>
        ))}
      </div>

      {/* Agents Overview */}
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold">8大核心Agent</h2>
          <button
            onClick={() => onNavigate('agents')}
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            查看详情 →
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="bg-slate-800/30 border border-slate-700/30 rounded-lg p-4 hover:bg-slate-800/50 transition-all cursor-pointer"
              onClick={() => onNavigate('agents')}
            >
              <div className="text-3xl mb-2">{agent.icon}</div>
              <h3 className="font-semibold text-sm mb-1">{agent.nameCn}</h3>
              <p className="text-xs text-slate-400 line-clamp-2">{agent.role}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Workflow Preview */}
      <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-8">
        <h2 className="text-2xl font-bold mb-6 text-center">10步自主成交流程</h2>
        <div className="flex items-center justify-between gap-2 overflow-x-auto pb-4">
          {[
            { step: 1, label: '任务接收', icon: '📨' },
            { step: 2, label: '线索聚合', icon: '📥' },
            { step: 3, label: '画像构建', icon: '👤' },
            { step: 4, label: '意图识别', icon: '🎯' },
            { step: 5, label: '策略生成', icon: '🧠' },
            { step: 6, label: '智能议价', icon: '💰' },
            { step: 7, label: '订单执行', icon: '📋' },
            { step: 8, label: '客户运营', icon: '📞' },
            { step: 9, label: '知识沉淀', icon: '💎' },
            { step: 10, label: '报告生成', icon: '📊' },
          ].map((item, idx) => (
            <div key={idx} className="flex items-center gap-2 flex-shrink-0">
              <div className="flex flex-col items-center gap-2">
                <div className="text-2xl">{item.icon}</div>
                <div className="text-xs text-slate-400 text-center w-16">{item.label}</div>
              </div>
              {idx < 9 && <div className="text-slate-600 text-xl">→</div>}
            </div>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div className="flex gap-4 justify-center">
        <button
          onClick={() => onNavigate('scenario')}
          className="px-6 py-3 bg-blue-500 hover:bg-blue-600 rounded-lg font-semibold transition-colors"
        >
          查看场景演示
        </button>
        <button
          onClick={() => onNavigate('architecture')}
          className="px-6 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg font-semibold transition-colors"
        >
          了解系统架构
        </button>
      </div>
    </div>
  )
}
