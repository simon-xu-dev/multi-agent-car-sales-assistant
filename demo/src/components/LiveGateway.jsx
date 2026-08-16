import { useState } from 'react'
import {
  healthCheck, resetScenario, callTool, fetchTrace, fetchLogs,
  fetchMetrics, archiveRun, makeTraceparent, genId,
} from '../lib/gatewayClient'
import { SCENARIOS, SCRIPTS, resolveBody, extractVars, RISK_CLS, ACTIVE_CLS } from '../data/liveScripts'
import AgentCollaboration from './AgentCollaboration'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const fmt = (v) => {
  try { return typeof v === 'string' ? v : JSON.stringify(v) } catch { return String(v) }
}
const short = (s) => (s ? String(s).slice(0, 8) : '—')
const LEVEL_CLS = { INFO: 'text-slate-300', WARN: 'text-yellow-400', ERROR: 'text-red-400' }

export default function LiveGateway() {
  const [baseUrl, setBaseUrl] = useState('http://127.0.0.1:18089')
  const [conn, setConn] = useState('unknown')
  const [scenarioIdx, setScenarioIdx] = useState(0)
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState([])
  const [traceId, setTraceId] = useState('')
  const [view, setView] = useState('trace')
  const [trace, setTrace] = useState([])
  const [logs, setLogs] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [archive, setArchive] = useState(null)
  const [error, setError] = useState('')

  const sc = SCENARIOS[scenarioIdx]
  const script = SCRIPTS[sc.id]

  async function testConn() {
    setError('')
    try {
      const r = await healthCheck(baseUrl)
      setConn(r.ok ? 'ok' : 'fail')
    } catch (e) {
      setConn('fail'); setError(e.message)
    }
  }

  async function runPipeline() {
    setError(''); setArchive(null); setRunning(true)
    const initSteps = script.map((s, i) => ({ ...s, idx: i, status: 'pending' }))
    setSteps(initSteps)
    try {
      await resetScenario(baseUrl, sc.id)
      const agentTraceId = genId(32)
      const parentSpanId = genId(16)
      const tp = makeTraceparent(agentTraceId, parentSpanId)
      setTraceId(agentTraceId)
      const vars = {}
      for (let i = 0; i < script.length; i++) {
        setSteps((prev) => prev.map((s) => (s.idx === i ? { ...s, status: 'running' } : s)))
        const step = script[i]
        const body = resolveBody(step.body, vars)
        try {
          const t0 = performance.now()
          const result = await callTool(baseUrl, sc.id, step.tool, body, tp)
          const dur = Math.round(performance.now() - t0)
          Object.assign(vars, extractVars(result, step.extract))
          setSteps((prev) => prev.map((s) => (s.idx === i
            ? { ...s, status: 'ok', preview: fmt(result).slice(0, 160), duration_ms: dur }
            : s)))
        } catch (e) {
          setSteps((prev) => prev.map((s) => (s.idx === i
            ? { ...s, status: 'error', error: e.message } : s)))
          throw e
        }
        await sleep(280)
      }
      // 拉取网关侧权威 trace/logs/metrics
      const [t, l, m] = await Promise.all([
        fetchTrace(baseUrl, sc.id), fetchLogs(baseUrl, sc.id), fetchMetrics(baseUrl, sc.id),
      ])
      setTrace(t.result || []); setLogs(l.result || []); setMetrics(m.result || null)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  async function doArchive() {
    setError('')
    try {
      const r = await archiveRun(baseUrl, sc.id, sc.dealId)
      setArchive(r.result)
      // 归档后刷新 logs（多出 evidence_archived 事件）
      const l = await fetchLogs(baseUrl, sc.id)
      setLogs(l.result || [])
    } catch (e) { setError(e.message) }
  }

  const okCount = steps.filter((s) => s.status === 'ok').length
  const errCount = steps.filter((s) => s.status === 'error').length

  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold">实时网关演示</h1>
        <p className="text-slate-400 max-w-2xl mx-auto">
          连接真实运行的 Mock 工具网关（tools/mock_tool_server.py），驱动 AgentTeams 闭环管线，
          实时查看 Agent 协同拓扑、OpenTelemetry Trace / Log / Metrics 与证据归档
        </p>
      </div>

      {/* Agent 协同拓扑（实时） */}
      <AgentCollaboration
        activeAgents={steps.filter((s) => s.status === 'running' || s.status === 'ok').map((s) => s.agent)}
        activeStep={steps.findIndex((s) => s.status === 'running')}
        currentRisk={steps.find((s) => s.status === 'running')?.risk || ''}
      />

      {/* 网关连接 */}
      <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-5">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-slate-400">网关地址</label>
          <input
            value={baseUrl}
            onChange={(e) => { setBaseUrl(e.target.value); setConn('unknown') }}
            className="flex-1 min-w-[280px] bg-slate-900/60 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono focus:border-blue-500 outline-none"
            placeholder="http://127.0.0.1:18089"
          />
          <button
            onClick={testConn}
            className="px-4 py-2 bg-slate-700 rounded-lg text-sm hover:bg-slate-600 transition-colors"
          >
            测试连接
          </button>
          <span className={`text-xs px-2 py-1 rounded ${
            conn === 'ok' ? 'bg-green-500/20 text-green-400'
              : conn === 'fail' ? 'bg-red-500/20 text-red-400'
              : 'bg-slate-700 text-slate-400'}`}>
            {conn === 'ok' ? '● 已连接' : conn === 'fail' ? '● 连接失败' : '○ 未测试'}
          </span>
        </div>
        <p className="text-xs text-slate-500 mt-2">
          启动网关：<code className="text-slate-400">python3 tools/mock_tool_server.py --host 127.0.0.1 --port 18089</code>
        </p>
      </div>

      {/* 场景选择 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {SCENARIOS.map((s, idx) => (
          <button
            key={s.id}
            disabled={running}
            onClick={() => { setScenarioIdx(idx); setSteps([]); setTrace([]); setLogs([]); setMetrics(null); setArchive(null) }}
            className={`p-5 rounded-xl border transition-all text-left disabled:opacity-50 ${
              scenarioIdx === idx
                ? ACTIVE_CLS[s.cls]
                : 'bg-slate-800/30 border-slate-700/30 hover:bg-slate-800/50'
            }`}
          >
            <div className="text-xs text-slate-500 mb-1">{s.dealId}</div>
            <h3 className="font-semibold mb-1">{s.title}</h3>
            <p className="text-xs text-slate-400">{s.path}</p>
          </button>
        ))}
      </div>

      {/* 运行控制 */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={runPipeline}
          disabled={running || conn === 'fail'}
          className="px-6 py-2.5 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-lg hover:bg-blue-500/30 transition-colors disabled:opacity-50 font-medium"
        >
          {running ? '运行中…' : '▶ 运行实时演示'}
        </button>
        <button
          onClick={doArchive}
          disabled={running || !trace.length}
          className="px-4 py-2.5 bg-orange-500/20 text-orange-400 border border-orange-500/30 rounded-lg hover:bg-orange-500/30 transition-colors disabled:opacity-50 text-sm"
        >
          📦 归档证据（OSS Skill）
        </button>
        {steps.length > 0 && (
          <span className="text-xs text-slate-400">
            进度：{okCount}/{steps.length} 成功{errCount ? ` · ${errCount} 失败` : ''}
          </span>
        )}
        {traceId && <span className="text-xs text-slate-500 font-mono">trace_id: {short(traceId)}…</span>}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
          ⚠ {error}
        </div>
      )}

      {/* 实时执行步骤 */}
      {steps.length > 0 && (
        <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-5">
          <h3 className="font-semibold mb-4 text-cyan-400">AgentTeams 闭环管线协同</h3>
          <div className="space-y-2">
            {steps.map((s) => (
              <div key={s.idx} className="flex items-start gap-3 border-l-2 pl-3 py-1"
                style={{ borderColor: s.status === 'error' ? '#ef4444' : s.status === 'ok' ? '#22c55e' : '#64748b' }}>
                <div className="flex-shrink-0 w-6 text-center text-xs text-slate-500 mt-0.5">{s.idx + 1}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-slate-400">{s.agent}</span>
                    <span className="text-sm">{s.label}</span>
                    <span className="text-xs font-mono text-blue-400">{s.tool}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${RISK_CLS[s.risk]}`}>{s.risk}</span>
                    {s.status === 'running' && <span className="text-xs text-yellow-400 animate-pulse">● 运行中</span>}
                    {s.status === 'ok' && <span className="text-xs text-green-400">✓ {s.duration_ms}ms</span>}
                    {s.status === 'error' && <span className="text-xs text-red-400">✗ {s.error}</span>}
                  </div>
                  {s.preview && <div className="text-xs text-slate-500 mt-0.5 truncate font-mono">{s.preview}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 归档结果 */}
      {archive && (
        <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4 text-sm">
          <div className="text-orange-400 font-medium mb-2">📦 证据已归档（OSS 等价本地 bucket）</div>
          <div className="text-xs text-slate-400 space-y-1 font-mono">
            <div>object_key: {archive.object_key}</div>
            <div>etag: {archive.etag} · size: {archive.size_bytes} bytes · skill: {archive.skill}</div>
          </div>
        </div>
      )}

      {/* Trace / Logs / Metrics 面板 */}
      {trace.length > 0 && (
        <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-5">
          <div className="flex gap-2 mb-4 border-b border-slate-700/30 pb-3">
            {[['trace', '🔍 Trace', trace.length], ['logs', '📜 Logs', logs.length], ['metrics', '📊 Metrics', null]].map(([id, label, n]) => (
              <button key={id} onClick={() => setView(id)}
                className={`px-4 py-1.5 rounded-lg text-sm transition-colors ${view === id ? 'bg-blue-500/20 text-blue-400' : 'text-slate-400 hover:bg-slate-800'}`}>
                {label}{n != null && <span className="ml-1 text-xs">({n})</span>}
              </button>
            ))}
          </div>

          {view === 'trace' && (
            <div className="space-y-2 max-h-[520px] overflow-y-auto">
              {trace.map((c, i) => (
                <div key={i} className="border-l-2 pl-3 py-1.5" style={{
                  borderColor: c.status === 'error' ? '#ef4444' : c.span_kind === 'rag' ? '#a855f7' : '#3b82f6',
                }}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-slate-500">{new Date(c.time).toLocaleTimeString('zh-CN')}</span>
                    <span className="text-xs font-mono px-1.5 py-0.5 bg-slate-700 rounded">{c.tool}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${c.status === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}`}>{c.status}</span>
                    {c.span_kind && <span className="text-xs px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">{c.span_kind}</span>}
                    {c.duration_ms != null && <span className="text-xs text-slate-500">{c.duration_ms}ms</span>}
                    {c.parent_span_id && <span className="text-xs text-slate-600">← {short(c.parent_span_id)}</span>}
                  </div>
                  {c.args && Object.keys(c.args).length > 0 && (
                    <div className="text-xs text-slate-500 mt-1"><span className="text-slate-600">args:</span> <code>{JSON.stringify(c.args)}</code></div>
                  )}
                  <div className="text-xs text-slate-400 mt-1 truncate font-mono"><span className="text-slate-600">ret:</span> {c.result_preview}</div>
                </div>
              ))}
            </div>
          )}

          {view === 'logs' && (
            <div className="space-y-1.5 max-h-[520px] overflow-y-auto">
              {logs.map((l, i) => (
                <div key={i} className="text-xs font-mono flex gap-3 border-b border-slate-800/50 pb-1">
                  <span className={`font-semibold ${LEVEL_CLS[l.level] || 'text-slate-300'}`}>{l.level}</span>
                  <span className="text-slate-300">{l.event}</span>
                  {l.span_id && <span className="text-slate-600">span={short(l.span_id)}</span>}
                  {l.attributes && <span className="text-slate-500 truncate">{JSON.stringify(l.attributes)}</span>}
                </div>
              ))}
              {logs.length === 0 && <div className="text-sm text-slate-500">暂无结构化日志</div>}
            </div>
          )}

          {view === 'metrics' && metrics && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  ['tool_calls', metrics.tool_calls],
                  ['tool_success', metrics.tool_success],
                  ['tool_failure', metrics.tool_failure],
                  ['success_rate', (metrics.tool_success_rate ?? 0).toFixed(4)],
                ].map(([k, v]) => (
                  <div key={k} className="bg-slate-900/50 rounded-lg p-3 text-center">
                    <div className="text-xs text-slate-500">{k}</div>
                    <div className="text-xl font-bold text-blue-400">{v}</div>
                  </div>
                ))}
              </div>
              {metrics.by_kind && (
                <div>
                  <div className="text-xs text-slate-500 mb-1">span_kind 分布</div>
                  <div className="flex gap-2">
                    {Object.entries(metrics.by_kind).map(([k, v]) => (
                      <span key={k} className="text-xs px-2 py-1 bg-slate-700 rounded">{k}: {v}</span>
                    ))}
                  </div>
                </div>
              )}
              {metrics.by_tool && Object.keys(metrics.by_tool).length > 0 && (
                <div>
                  <div className="text-xs text-slate-500 mb-2">工具调用计数</div>
                  <div className="space-y-1">
                    {Object.entries(metrics.by_tool).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                      <div key={k} className="flex items-center gap-2 text-xs">
                        <span className="font-mono text-slate-400 w-64 truncate">{k}</span>
                        <div className="flex-1 bg-slate-900/50 rounded h-4 overflow-hidden">
                          <div className="h-full bg-blue-500/40" style={{ width: `${(v / metrics.tool_calls) * 100}%` }} />
                        </div>
                        <span className="text-slate-300 w-6 text-right">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
