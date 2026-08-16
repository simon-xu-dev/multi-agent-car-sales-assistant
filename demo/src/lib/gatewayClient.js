// CarSales mock tool gateway (tools/mock_tool_server.py) 的浏览器 HTTP 客户端。
// 网关已开启 CORS（Access-Control-Allow-Origin: *，GET/POST/OPTIONS），浏览器可直接调用。

/** 生成 W3C traceparent：version-trace_id-parent_id-flags，用于把 Agent 层 span
 *  作为工具 span 的 parent，形成统一 trace 树（网关 _parse_traceparent 解析）。 */
export function makeTraceparent(traceId, parentSpanId) {
  return `00-${traceId}-${parentSpanId}-01`
}

/** 生成 hex 随机串（trace_id 32 位 / span_id 16 位）。 */
export function genId(hexLen) {
  const bytes = new Uint8Array(hexLen / 2)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

export async function healthCheck(base) {
  const r = await fetch(`${base}/health`)
  if (!r.ok) throw new Error(`health ${r.status}`)
  return r.json()
}

export async function resetScenario(base, sid) {
  const r = await fetch(`${base}/tools/${sid}/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  if (!r.ok) throw new Error(`reset ${r.status}`)
  return r.json()
}

export async function callTool(base, sid, tool, body, traceparent) {
  const headers = { 'Content-Type': 'application/json' }
  if (traceparent) headers.traceparent = traceparent
  const r = await fetch(`${base}/tools/${sid}/${tool}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body || {}),
  })
  const j = await r.json()
  if (!r.ok || !j.ok) {
    const err = new Error(j.error || `call ${tool} ${r.status}`)
    err.payload = j
    throw err
  }
  return j.result
}

export async function fetchTrace(base, sid) {
  const r = await fetch(`${base}/tools/${sid}/trace`)
  if (!r.ok) throw new Error(`trace ${r.status}`)
  return r.json()
}

export async function fetchLogs(base, sid) {
  const r = await fetch(`${base}/tools/${sid}/logs`)
  if (!r.ok) throw new Error(`logs ${r.status}`)
  return r.json()
}

export async function fetchMetrics(base, sid) {
  const r = await fetch(`${base}/tools/${sid}/metrics`)
  if (!r.ok) throw new Error(`metrics ${r.status}`)
  return r.json()
}

export async function archiveRun(base, sid, dealId) {
  const r = await fetch(`${base}/tools/${sid}/archive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ deal_id: dealId }),
  })
  if (!r.ok) throw new Error(`archive ${r.status}`)
  return r.json()
}
