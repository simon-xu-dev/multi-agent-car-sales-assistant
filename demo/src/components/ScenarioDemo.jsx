import { useState } from 'react'
import familySuv from '../data/family_suv_deal.json'
import firstCar from '../data/first_car_finance.json'
import tradeIn from '../data/trade_in_renewal.json'
import deal2001Trace from '../data/DEAL-2001_trace.json'
import deal2002Trace from '../data/DEAL-2002_trace_full.json'
import deal2003Trace from '../data/DEAL-2003_trace.json'
import teamSpec from '../data/team_spec.json'

const scenarios = [
  { id: 'DEAL-2001', data: familySuv, trace: deal2001Trace, activeCls: 'bg-blue-500/20 border-blue-500/50' },
  { id: 'DEAL-2002', data: firstCar, trace: deal2002Trace, activeCls: 'bg-purple-500/20 border-purple-500/50' },
  { id: 'DEAL-2003', data: tradeIn, trace: deal2003Trace, activeCls: 'bg-green-500/20 border-green-500/50' },
]

export default function ScenarioDemo() {
  const [selectedScenario, setSelectedScenario] = useState(0)
  const [showTrace, setShowTrace] = useState(false)

  const scenario = scenarios[selectedScenario]
  const { data, trace } = scenario

  return (
    <div className="space-y-8">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold">场景演示</h1>
        <p className="text-slate-400 max-w-2xl mx-auto">
          3个真实交易场景，展示从客户咨询到成交的全链路Agent协作过程
        </p>
      </div>

      {/* Scenario Selection */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {scenarios.map((s, idx) => (
          <button
            key={s.id}
            onClick={() => {
              setSelectedScenario(idx)
              setShowTrace(false)
            }}
            className={`p-6 rounded-xl border transition-all text-left ${
              selectedScenario === idx
                ? s.activeCls
                : 'bg-slate-800/30 border-slate-700/30 hover:bg-slate-800/50'
            }`}
          >
            <div className="text-xs text-slate-500 mb-2">{s.id}</div>
            <h3 className="font-semibold mb-2">{s.data.customer.name}</h3>
            <p className="text-sm text-slate-400 line-clamp-2">{s.data.title}</p>
          </button>
        ))}
      </div>

      {/* Scenario Details */}
      <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-8">
        <div className="space-y-6">
          {/* Customer Info */}
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-2xl font-bold mb-2">{data.title}</h2>
              <div className="flex gap-4 text-sm text-slate-400">
                <span>👤 {data.customer.name}</span>
                <span>🏪 {data.customer.store}</span>
                <span>💼 {data.customer.owner}</span>
              </div>
            </div>
            <button
              onClick={() => setShowTrace(!showTrace)}
              className="px-4 py-2 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-lg hover:bg-blue-500/30 transition-colors"
            >
              {showTrace ? '隐藏Trace' : '查看Trace'} ({trace.result.length}次调用)
            </button>
          </div>

          {/* Customer Profile */}
          <div className="bg-slate-800/50 rounded-lg p-6">
            <h3 className="font-semibold mb-3 text-blue-400">客户画像</h3>
            <p className="text-sm text-slate-300">{data.customer.profile_hint}</p>
            <div className="grid grid-cols-2 gap-4 mt-4">
              <div>
                <div className="text-xs text-slate-500 mb-1">预算</div>
                <div className="text-sm">{data.lead.budget_hint}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">线索来源</div>
                <div className="text-sm">{data.lead.source}</div>
              </div>
            </div>
          </div>

          {/* Multi-channel Sessions */}
          <div className="bg-slate-800/50 rounded-lg p-6">
            <h3 className="font-semibold mb-3 text-purple-400">多渠道会话记录</h3>
            <div className="space-y-3">
              {data.sessions.map((session, idx) => (
                <div key={idx} className="flex gap-4">
                  <div className="flex-shrink-0 w-20 text-xs text-slate-500">
                    {session.time}
                  </div>
                  <div className="flex-shrink-0 w-20">
                    <span className="px-2 py-1 bg-slate-700 rounded text-xs">
                      {session.channel}
                    </span>
                  </div>
                  <div className="flex-1 text-sm text-slate-300">{session.text}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Recommended Models */}
          <div className="bg-slate-800/50 rounded-lg p-6">
            <h3 className="font-semibold mb-3 text-green-400">推荐车型</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {data.models.map((model, idx) => (
                <div key={idx} className="bg-slate-900/50 rounded-lg p-4">
                  <h4 className="font-semibold mb-2">{model.name}</h4>
                  <div className="text-xs text-slate-400 space-y-1">
                    <div>{model.category}</div>
                    <div className="text-green-400">
                      ¥{model.guide_price.toLocaleString()}
                    </div>
                    <div className="flex gap-1 flex-wrap mt-2">
                      {model.tags.map((tag, tidx) => (
                        <span key={tidx} className="px-2 py-0.5 bg-slate-700 rounded text-xs">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Expected Outcome */}
          <div className="bg-slate-800/50 rounded-lg p-6">
            <h3 className="font-semibold mb-3 text-orange-400">预期结果</h3>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-slate-500">推荐车型：</span>
                <span className="text-slate-300">{data.expected_outcome.recommended_models.join('、')}</span>
              </div>
              <div>
                <div className="text-slate-500 mb-1">自动执行（L0/L1）：</div>
                <div className="flex gap-2 flex-wrap">
                  {data.expected_outcome.low_risk_auto.map((item, idx) => (
                    <span key={idx} className="px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-slate-500 mb-1">需审批（L2）：</div>
                <div className="flex gap-2 flex-wrap">
                  {data.expected_outcome.approval_required.map((item, idx) => (
                    <span key={idx} className="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-xs">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Workflow Steps */}
          <div className="bg-slate-800/50 rounded-lg p-6">
            <h3 className="font-semibold mb-3 text-cyan-400">10步Agent协作流程</h3>
            <div className="space-y-2">
              {teamSpec.workflow.map((step, idx) => (
                <div key={idx} className="flex items-center gap-3">
                  <div className="flex-shrink-0 w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center text-xs font-semibold">
                    {step.step}
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium">{step.agent}</div>
                    <div className="text-xs text-slate-400">{step.task}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Trace Timeline */}
          {showTrace && (
            <div className="bg-slate-800/50 rounded-lg p-6">
              <h3 className="font-semibold mb-3 text-pink-400">
                工具调用Trace时间线 ({trace.result.length}次调用)
              </h3>
              <div className="space-y-3">
                {trace.result.map((call, idx) => {
                  const time = new Date(call.time).toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })
                  return (
                    <div key={idx} className="border-l-2 border-slate-700 pl-4 py-2">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-slate-500">{time}</span>
                        <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs font-mono">
                          {call.tool}
                        </span>
                      </div>
                      {call.args && Object.keys(call.args).length > 0 && (
                        <div className="text-xs text-slate-400 mt-1">
                          <span className="text-slate-500">参数：</span>
                          <code className="ml-1">{JSON.stringify(call.args)}</code>
                        </div>
                      )}
                      <div className="text-xs text-slate-400 mt-1">
                        <span className="text-slate-500">返回：</span>
                        <code className="ml-1 line-clamp-2">{call.result_preview}</code>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
