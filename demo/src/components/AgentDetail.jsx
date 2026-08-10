import { agents } from '../data/agents'
import teamSpec from '../data/team_spec.json'

export default function AgentDetail() {
  return (
    <div className="space-y-8">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold">Agent详情</h1>
        <p className="text-slate-400 max-w-2xl mx-auto">
          8大专业Agent，各司其职，协同完成从线索到成交的全链路闭环
        </p>
      </div>

      {/* Agent Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {agents.map((agent) => {
          const workflowStep = teamSpec.workflow.find((w) => w.agent === agent.id)
          return (
            <div
              key={agent.id}
              className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-6 hover:border-slate-600 transition-all"
            >
              <div className="flex items-start gap-4 mb-4">
                <div
                  className="text-4xl p-3 rounded-lg"
                  style={{ backgroundColor: `${agent.color}20` }}
                >
                  {agent.icon}
                </div>
                <div className="flex-1">
                  <h3 className="text-xl font-bold mb-1">{agent.nameCn}</h3>
                  <p className="text-sm text-slate-400">{agent.name}</p>
                  {workflowStep && (
                    <div className="mt-2 inline-block px-2 py-1 bg-slate-700 rounded text-xs">
                      Step {workflowStep.step}
                    </div>
                  )}
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <h4 className="text-sm font-semibold text-slate-300 mb-2">职责定位</h4>
                  <p className="text-sm text-slate-400">{agent.role}</p>
                </div>

                <div>
                  <h4 className="text-sm font-semibold text-slate-300 mb-2">Skills</h4>
                  <div className="flex gap-2 flex-wrap">
                    {agent.skills.map((skill, idx) => (
                      <span
                        key={idx}
                        className="px-3 py-1 bg-purple-500/20 text-purple-400 rounded-full text-xs"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <h4 className="text-sm font-semibold text-slate-300 mb-2">Tools</h4>
                  <div className="flex gap-2 flex-wrap">
                    {agent.tools.map((tool, idx) => (
                      <span
                        key={idx}
                        className="px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full text-xs font-mono"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>

                {workflowStep && (
                  <div>
                    <h4 className="text-sm font-semibold text-slate-300 mb-2">任务描述</h4>
                    <p className="text-xs text-slate-400 font-mono bg-slate-900/50 p-2 rounded">
                      {workflowStep.task}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* TeamLeader */}
      <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-500/30 rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="text-4xl p-3 bg-purple-500/20 rounded-lg">🎯</div>
          <div className="flex-1">
            <h3 className="text-xl font-bold mb-2 text-purple-400">TeamLeader</h3>
            <p className="text-sm text-slate-400 mb-4">{teamSpec.team.team_leader.name}</p>
            <div className="space-y-3">
              <div>
                <h4 className="text-sm font-semibold text-slate-300 mb-2">核心职责</h4>
                <ul className="text-sm text-slate-400 space-y-1">
                  <li>• 接收Manager分发的交易任务</li>
                  <li>• 拆解任务并分发给8个业务Worker</li>
                  <li>• 传递上下文与历史信息</li>
                  <li>• 汇总各Worker执行结果</li>
                  <li>• 生成最终交易报告</li>
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-semibold text-slate-300 mb-2">Workflow步骤</h4>
                <div className="space-y-2">
                  {teamSpec.workflow
                    .filter((w) => w.agent === 'carsales_demo_leader')
                    .map((step, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <span className="text-xs text-slate-500">Step {step.step}</span>
                        <span className="text-sm text-slate-300">{step.task}</span>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Creation Policy */}
      <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-6">
        <h2 className="text-xl font-bold mb-4">Worker创建策略</h2>
        <div className="space-y-3 text-sm">
          <div className="flex items-start gap-3">
            <span className="text-slate-500 flex-shrink-0">模式：</span>
            <span className="text-slate-300">{teamSpec.team.creation_policy.mode}</span>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-slate-500 flex-shrink-0">顺序：</span>
            <div className="flex gap-2 flex-wrap">
              {teamSpec.team.creation_policy.order.map((agent, idx) => (
                <span key={idx} className="px-2 py-1 bg-slate-700 rounded text-xs">
                  {agent}
                </span>
              ))}
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-slate-500 flex-shrink-0">规则：</span>
            <span className="text-slate-300">{teamSpec.team.creation_policy.rule}</span>
          </div>
        </div>
      </div>

      {/* Risk Policy */}
      <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-6">
        <h2 className="text-xl font-bold mb-4">风险控制策略</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <h4 className="font-semibold text-green-400 mb-2">自动执行</h4>
            <p className="text-slate-400">{teamSpec.risk_policy.auto_execute.join(', ')}</p>
          </div>
          <div>
            <h4 className="font-semibold text-yellow-400 mb-2">仅审批</h4>
            <p className="text-slate-400">{teamSpec.risk_policy.approval_only.join(', ')}</p>
          </div>
          <div>
            <h4 className="font-semibold text-red-400 mb-2">升级至人工</h4>
            <p className="text-slate-400">{teamSpec.risk_policy.escalate_to_human}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
