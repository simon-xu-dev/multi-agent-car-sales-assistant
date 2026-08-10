export default function Architecture() {
  return (
    <div className="space-y-8">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold">系统架构</h1>
        <p className="text-slate-400 max-w-2xl mx-auto">
          基于AgentTeams框架的多层协同架构，实现Manager → TeamLeader → Workers的分层调度
        </p>
      </div>

      {/* Architecture Diagram */}
      <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-8">
        <div className="space-y-8">
          {/* Manager Layer */}
          <div className="text-center">
            <div className="inline-block bg-gradient-to-r from-blue-500/20 to-cyan-500/20 border border-blue-500/30 rounded-xl p-6">
              <div className="text-3xl mb-2">👔</div>
              <h3 className="text-xl font-bold text-blue-400">Manager</h3>
              <p className="text-sm text-slate-400 mt-2">AgentTeams运行时管理器</p>
              <p className="text-xs text-slate-500 mt-1">负责Worker创建、健康检查、任务分发</p>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <div className="text-4xl text-slate-600">↓</div>
          </div>

          {/* TeamLeader Layer */}
          <div className="text-center">
            <div className="inline-block bg-gradient-to-r from-purple-500/20 to-pink-500/20 border border-purple-500/30 rounded-xl p-6">
              <div className="text-3xl mb-2">🎯</div>
              <h3 className="text-xl font-bold text-purple-400">TeamLeader</h3>
              <p className="text-sm text-slate-400 mt-2">carsales-demo-leader</p>
              <p className="text-xs text-slate-500 mt-1">任务拆解、上下文传递、结果汇总、报告生成</p>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <div className="text-4xl text-slate-600">↓</div>
          </div>

          {/* Workers Layer */}
          <div className="space-y-4">
            <h3 className="text-center text-lg font-semibold text-slate-300">8大业务Worker</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { icon: '📥', name: 'Lead Intake', desc: '线索聚合', cls: 'bg-blue-500/10 border-blue-500/30' },
                { icon: '👤', name: 'Profile Builder', desc: '画像构建', cls: 'bg-purple-500/10 border-purple-500/30' },
                { icon: '🎯', name: 'Intent Analyst', desc: '意图识别', cls: 'bg-pink-500/10 border-pink-500/30' },
                { icon: '🧠', name: 'Strategy Planner', desc: '策略生成', cls: 'bg-orange-500/10 border-orange-500/30' },
                { icon: '💰', name: 'Negotiation', desc: '智能议价', cls: 'bg-green-500/10 border-green-500/30' },
                { icon: '📋', name: 'Order Executor', desc: '订单执行', cls: 'bg-cyan-500/10 border-cyan-500/30' },
                { icon: '📞', name: 'Customer Ops', desc: '客户运营', cls: 'bg-amber-500/10 border-amber-500/30' },
                { icon: '💎', name: 'Knowledge Miner', desc: '知识沉淀', cls: 'bg-indigo-500/10 border-indigo-500/30' },
              ].map((worker, idx) => (
                <div
                  key={idx}
                  className={`${worker.cls} rounded-lg p-4 text-center`}
                >
                  <div className="text-2xl mb-2">{worker.icon}</div>
                  <h4 className="font-semibold text-sm">{worker.name}</h4>
                  <p className="text-xs text-slate-400 mt-1">{worker.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <div className="text-4xl text-slate-600">↓</div>
          </div>

          {/* Tool Gateway Layer */}
          <div className="text-center">
            <div className="inline-block bg-gradient-to-r from-orange-500/20 to-red-500/20 border border-orange-500/30 rounded-xl p-6">
              <div className="text-3xl mb-2">🔌</div>
              <h3 className="text-xl font-bold text-orange-400">Mock Tool Gateway</h3>
              <p className="text-sm text-slate-400 mt-2">HTTP工具网关 (Port 18089)</p>
              <div className="flex gap-2 mt-3 justify-center flex-wrap">
                {['CRM', '知识库', '库存', '价格', '金融', '试驾', '订单'].map((tool, idx) => (
                  <span key={idx} className="px-3 py-1 bg-slate-800 rounded-full text-xs text-slate-300">
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Data Flow */}
      <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-8">
        <h2 className="text-2xl font-bold mb-6 text-center">数据流向</h2>
        <div className="space-y-4">
          {[
            { step: '1', label: '客户咨询', desc: '多渠道接入（官网/微信/电话/抖音）', icon: '💬' },
            { step: '2', label: '线索聚合', desc: '融合多会话，生成统一线索并评分', icon: '📥' },
            { step: '3', label: '画像构建', desc: '基于历史行为构建客户画像，标注置信度', icon: '👤' },
            { step: '4', label: '意图识别', desc: 'BANT框架评估意向，输出优先级', icon: '🎯' },
            { step: '5', label: '策略生成', desc: '推荐车型、生成报价、规划跟进路径', icon: '🧠' },
            { step: '6', label: '智能议价', desc: '执行低风险动作，高风险动作触发审批', icon: '💰' },
            { step: '7', label: '订单执行', desc: '创建订单草稿，验证交易合规性', icon: '📋' },
            { step: '8', label: '客户运营', desc: '售后触达、战败激活、复购引导', icon: '📞' },
            { step: '9', label: '知识沉淀', desc: '挖掘成交案例，沉淀为可复用知识', icon: '💎' },
            { step: '10', label: '报告生成', desc: 'TeamLeader汇总生成最终成交报告', icon: '📊' },
          ].map((item, idx) => (
            <div key={idx} className="flex items-center gap-4 bg-slate-800/50 rounded-lg p-4">
              <div className="text-3xl">{item.icon}</div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">Step {item.step}</span>
                  <h4 className="font-semibold">{item.label}</h4>
                </div>
                <p className="text-sm text-slate-400 mt-1">{item.desc}</p>
              </div>
              {idx < 9 && (
                <div className="text-slate-600 text-2xl">→</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Risk Policy */}
      <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-8">
        <h2 className="text-2xl font-bold mb-6 text-center">风险控制策略</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-6">
            <div className="text-2xl mb-2">✅</div>
            <h3 className="font-bold text-green-400 mb-2">L0/L1 自动执行</h3>
            <p className="text-sm text-slate-400">
              低风险动作：线索聚合、画像构建、标准报价、试驾预约等，Agent自主完成
            </p>
          </div>
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-6">
            <div className="text-2xl mb-2">⚠️</div>
            <h3 className="font-bold text-yellow-400 mb-2">L2 人工审批</h3>
            <p className="text-sm text-slate-400">
              中风险动作：超授权优惠、征信授权、订单创建等，需人工审批后执行
            </p>
          </div>
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6">
            <div className="text-2xl mb-2">🛑</div>
            <h3 className="font-bold text-red-400 mb-2">L3 人工介入</h3>
            <p className="text-sm text-slate-400">
              高风险动作：议价触底、客户投诉等，Agent停止自动让步并转人工销售
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
