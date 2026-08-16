// 每个场景的 AgentTeams 闭环管线定义：按 AgentTeams 协同顺序定义工具调用链路，
// 对应 TeamLeader DAG 拆解的真实 Agent 推理→工具调用序列。
// body 内 {{var}} 占位符由前序步骤的 extract 结果注入（如 quote_id / slot / plan_id）。

function getPath(obj, path) {
  return path.split('.').reduce((acc, key) => {
    if (acc == null) return undefined
    const k = Array.isArray(acc) ? parseInt(key, 10) : key
    return Number.isNaN(k) ? acc?.[key] : acc?.[k]
  }, obj)
}

export const SCENARIOS = [
  { id: 'family_suv_deal', dealId: 'DEAL-2001', title: '家庭 SUV 全链路成交', path: 'new_deal 全链路', cls: 'blue' },
  { id: 'first_car_finance', dealId: 'DEAL-2002', title: '首购金融专项', path: 'finance 跳过线索归并', cls: 'purple' },
  { id: 'trade_in_renewal', dealId: 'DEAL-2003', title: '老客置换与售后', path: 'trade_in 直达记忆召回', cls: 'green' },
]

export const SCRIPTS = {
  family_suv_deal: [
    { agent: 'lead-intake', label: '多渠道会话归并', tool: 'mock_crm.list_sessions', body: {}, risk: 'L0' },
    { agent: 'lead-intake', label: '线索查询', tool: 'mock_crm.get_lead', body: { lead_id: 'LEAD-2001' }, risk: 'L0' },
    { agent: 'lead-intake', label: '客户历史召回', tool: 'mock_crm.get_customer_history', body: { customer_id: 'CUST-2001' }, risk: 'L0' },
    { agent: 'profile-builder', label: '产品 RAG 检索', tool: 'mock_knowledge.search_product', body: { query: '新能源六座SUV' }, risk: 'L0' },
    { agent: 'intent-analyst', label: '成交案例 RAG', tool: 'mock_knowledge.search_case', body: { query: '二胎家庭SUV六座' }, risk: 'L0' },
    { agent: 'intent-analyst', label: 'SOP 检索（成交信号）', tool: 'mock_knowledge.search_sop', body: { query: '家庭SUV成交信号' }, risk: 'L0' },
    { agent: 'lead-intake', label: '线索状态流转', tool: 'mock_crm.update_lead_stage', body: { lead_id: 'LEAD-2001', stage: 'contacted' }, risk: 'L1' },
    { agent: 'strategy-planner', label: '车型目录', tool: 'mock_inventory.list_models', body: {}, risk: 'L0' },
    { agent: 'strategy-planner', label: '库存校验 L7', tool: 'mock_inventory.check_stock', body: { model_code: 'L7', store_id: 'store_001' }, risk: 'L0' },
    { agent: 'strategy-planner', label: '报价政策', tool: 'mock_price.get_policy', body: {}, risk: 'L0' },
    { agent: 'strategy-planner', label: '生成报价', tool: 'mock_price.calc_quote', body: { model_code: 'L7', customer_tier: 'normal' }, risk: 'L1', extract: { quote_id: 'quote_id' } },
    { agent: 'negotiation-executor', label: '授权内优惠（L1 自动）', tool: 'mock_price.apply_discount', body: { quote_id: '{{quote_id}}', amount: 2000, reason: '老客置换意向' }, risk: 'L1' },
    { agent: 'negotiation-executor', label: '试驾档期', tool: 'mock_testdrive.list_slots', body: { store_id: 'store_001', model_code: 'L7' }, risk: 'L0', extract: { slot: '0.slot' } },
    { agent: 'negotiation-executor', label: '试驾预约（L1 自动）', tool: 'mock_testdrive.book_slot', body: { customer_id: 'CUST-2001', store_id: 'store_001', slot: '{{slot}}', model_code: 'L7' }, risk: 'L1' },
    { agent: 'negotiation-executor', label: '库存预留（L1 自动）', tool: 'mock_inventory.reserve_car', body: { model_code: 'L7', store_id: 'store_001' }, risk: 'L1' },
    { agent: 'order-executor', label: '订单草稿（L2 审批）', tool: 'mock_order.create_order', body: { lead_id: 'LEAD-2001', quote_id: '{{quote_id}}', order_key: 'KEY-LIVE-2001' }, risk: 'L2' },
    { agent: 'order-executor', label: '闭环验证 check_deal', tool: 'mock_verify.check_deal', body: { deal_id: 'DEAL-2001' }, risk: 'L0' },
  ],
  first_car_finance: [
    { agent: 'profile-builder', label: '画像：线索查询', tool: 'mock_crm.get_lead', body: { lead_id: 'LEAD-2002' }, risk: 'L0' },
    { agent: 'profile-builder', label: '客户历史召回', tool: 'mock_crm.get_customer_history', body: { customer_id: 'CUST-2002' }, risk: 'L0' },
    { agent: 'strategy-planner', label: '车型目录', tool: 'mock_inventory.list_models', body: {}, risk: 'L0' },
    { agent: 'strategy-planner', label: '生成报价', tool: 'mock_price.calc_quote', body: { model_code: 'QIN', customer_tier: 'normal' }, risk: 'L1', extract: { quote_id: 'quote_id' } },
    { agent: 'negotiation-executor', label: '金融方案生成', tool: 'mock_finance.calc_plan', body: { price: 129800, down_payment: 40000, months: 36 }, risk: 'L0', extract: { plan_id: 'plans.0.plan_id' } },
    { agent: 'negotiation-executor', label: '征信授权审批（L2）', tool: 'mock_finance.submit_approval', body: { plan_id: '{{plan_id}}', customer_id: 'CUST-2002' }, risk: 'L2' },
    { agent: 'order-executor', label: '订单草稿（L2）', tool: 'mock_order.create_order', body: { lead_id: 'LEAD-2002', quote_id: '{{quote_id}}', order_key: 'KEY-LIVE-2002' }, risk: 'L2' },
    { agent: 'order-executor', label: '闭环验证', tool: 'mock_verify.check_deal', body: { deal_id: 'DEAL-2002' }, risk: 'L0' },
  ],
  trade_in_renewal: [
    { agent: 'profile-builder', label: '历史记忆召回（3 年老客）', tool: 'mock_crm.get_customer_history', body: { customer_id: 'CUST-2003' }, risk: 'L0' },
    { agent: 'profile-builder', label: '置换案例 RAG', tool: 'mock_knowledge.search_case', body: { query: '置换' }, risk: 'L0' },
    { agent: 'strategy-planner', label: '置换 SOP', tool: 'mock_knowledge.search_sop', body: { query: '置换' }, risk: 'L0' },
    { agent: 'strategy-planner', label: '车型目录', tool: 'mock_inventory.list_models', body: {}, risk: 'L0' },
    { agent: 'strategy-planner', label: '库存校验 TANG', tool: 'mock_inventory.check_stock', body: { model_code: 'TANG', store_id: 'store_003' }, risk: 'L0' },
    { agent: 'strategy-planner', label: '生成报价', tool: 'mock_price.calc_quote', body: { model_code: 'TANG', customer_tier: 'vip' }, risk: 'L1', extract: { quote_id: 'quote_id' } },
    { agent: 'negotiation-executor', label: '超授权让步（底线守护 L2）', tool: 'mock_price.apply_discount', body: { quote_id: '{{quote_id}}', amount: 30000, reason: '置换压价' }, risk: 'L2' },
    { agent: 'negotiation-executor', label: '试驾档期', tool: 'mock_testdrive.list_slots', body: { store_id: 'store_003', model_code: 'TANG' }, risk: 'L0', extract: { slot: '0.slot' } },
    { agent: 'negotiation-executor', label: '试驾预约（L1）', tool: 'mock_testdrive.book_slot', body: { customer_id: 'CUST-2003', store_id: 'store_003', slot: '{{slot}}', model_code: 'TANG' }, risk: 'L1' },
    { agent: 'order-executor', label: '订单草稿（L2）', tool: 'mock_order.create_order', body: { lead_id: 'LEAD-2003', quote_id: '{{quote_id}}', order_key: 'KEY-LIVE-2003' }, risk: 'L2' },
    { agent: 'order-executor', label: '闭环验证', tool: 'mock_verify.check_deal', body: { deal_id: 'DEAL-2003' }, risk: 'L0' },
  ],
}

export function resolveBody(body, vars) {
  const out = {}
  for (const [k, v] of Object.entries(body)) {
    if (typeof v === 'string' && v.startsWith('{{') && v.endsWith('}}')) {
      out[k] = vars[v.slice(2, -2)] ?? v
    } else {
      out[k] = v
    }
  }
  return out
}

export function extractVars(result, spec) {
  if (!spec) return {}
  const out = {}
  for (const [name, path] of Object.entries(spec)) out[name] = getPath(result, path)
  return out
}

export const RISK_CLS = {
  L0: 'bg-slate-600/40 text-slate-300',
  L1: 'bg-green-500/20 text-green-400',
  L2: 'bg-yellow-500/20 text-yellow-400',
  L3: 'bg-red-500/20 text-red-400',
}

// 场景选中态样式（完整字符串，避免 Tailwind JIT 动态拼接漏生成）
export const ACTIVE_CLS = {
  blue: 'bg-blue-500/20 border-blue-500/50',
  purple: 'bg-purple-500/20 border-purple-500/50',
  green: 'bg-green-500/20 border-green-500/50',
}
