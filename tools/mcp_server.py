"""CarSales MCP Server —— 以真实 MCP 协议暴露工具能力，复用 LocalMockTools 全部业务逻辑。

证明 MCP 等价契约（tools/MCP_MAPPING.md）的迁移成本仅限协议适配层：本 Server
直接复用 mock_tools.LocalMockTools（报价/优惠/审批门禁/订单/回滚/RAG），Agent 与
Skill 零改动即可从 HTTP mock 切换到 MCP 工具调用。生产环境把 LocalMockTools 换成
真实 CRM/DMS/金融适配器，MCP Server 本身不动。

传输：stdio（标准 MCP 本地接入方式）。
运行：python3 tools/mcp_server.py
接入：MCP 客户端（Claude Desktop / mcp CLI / 自研 Agent）按 stdio 连接。
验证：python3 tools/mcp_client_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mock_tools import LocalMockTools  # noqa: E402

mcp = FastMCP("car-sales")

DEFAULT_SCENARIO = "family_suv_deal"

# 按场景缓存工具实例：报价/订单/审批/预约状态需跨多次 MCP 调用持久
# （与 HTTP 网关 TOOL_STATES 同构；生产环境换成真实系统适配器实例池）
_STATE_CACHE: dict[str, LocalMockTools] = {}


def _tools(scenario_id: str) -> LocalMockTools:
    if scenario_id not in _STATE_CACHE:
        _STATE_CACHE[scenario_id] = LocalMockTools(scenario_id)
    return _STATE_CACHE[scenario_id]


# ---- CRM / 线索 ----
@mcp.tool()
def crm_lead_query(lead_id: Optional[str] = None, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """查询线索基本信息与状态。对应 HTTP mock: mock_crm.get_lead。"""
    return _tools(scenario_id).get_lead(lead_id)


@mcp.tool()
def crm_list_sessions(scenario_id: str = DEFAULT_SCENARIO) -> list:
    """列出多渠道会话（官网/微信/电话），供线索归并去重。对应 HTTP mock: mock_crm.list_sessions。"""
    return _tools(scenario_id).list_sessions()


@mcp.tool()
def crm_lead_stage_update(lead_id: str, stage: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """更新线索状态机（new→contacted→qualified→…→won）。状态变更为 L0，非资金动作。"""
    return _tools(scenario_id).update_lead_stage(lead_id, stage)


# ---- 库存 / DMS ----
@mcp.tool()
def inventory_list_models(scenario_id: str = DEFAULT_SCENARIO) -> list:
    """列出车型目录与库存。对应 HTTP mock: mock_inventory.list_models。"""
    return _tools(scenario_id).list_models()


@mcp.tool()
def inventory_check_stock(model_code: str, store_id: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """查询指定车型在门店的库存。store_id 支持别名归一化（如'杭州滨江旗舰店'）。"""
    return _tools(scenario_id).check_stock(model_code, store_id)


@mcp.tool()
def inventory_reserve_car(model_code: str, store_id: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """库存预留（L1 可逆，超时自动释放）。"""
    return _tools(scenario_id).reserve_car(model_code, store_id)


# ---- 报价与优惠（含审批门禁）----
@mcp.tool()
def pricing_policy_query(scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """查询报价政策（基础折扣/分层/授权上限）。对应 HTTP mock: mock_price.get_policy。"""
    return _tools(scenario_id).get_policy()


@mcp.tool()
def pricing_quote_calc(model_code: str, customer_tier: str = "normal", scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """在政策范围内生成标准报价。对应 HTTP mock: mock_price.calc_quote。"""
    return _tools(scenario_id).calc_quote(model_code, customer_tier)


@mcp.tool()
def pricing_discount_apply(quote_id: str, amount: float, reason: str = "", scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """申请优惠：授权内(L1)自动应用；超授权返回 needs_approval + 审批任务(L2)。对应 HTTP mock: mock_price.apply_discount。"""
    return _tools(scenario_id).apply_discount(quote_id, amount, reason)


# ---- 金融审批 ----
@mcp.tool()
def finance_plan_calc(price: float, down_payment: float, months: int, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """计算分期金融方案对比。对应 HTTP mock: mock_finance.calc_plan。"""
    return _tools(scenario_id).calc_plan(price, down_payment, months)


@mcp.tool()
def finance_approval_submit(plan_id: str, customer_id: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """发起征信授权审批（L2，必须人工审批，留痕审计）。对应 HTTP mock: mock_finance.submit_approval。"""
    return _tools(scenario_id).submit_approval(plan_id, customer_id)


@mcp.tool()
def approval_check(approval_id: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """查询审批任务当前状态（pending/approved/rejected）。对应 HTTP mock: mock_finance.check_approval。"""
    return _tools(scenario_id).check_approval(approval_id)


@mcp.tool()
def approval_approve(approval_id: str, approver: str = "store_manager", reason: str = "",
                     scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """审批通过（pending -> approved）：人工决策，全量写入审计轨迹，关联订单可进入 confirm。
    幂等——重复对已决策审批调用返回当前状态。对应 HTTP mock: mock_finance.approve。"""
    return _tools(scenario_id).approve(approval_id, approver, reason)


@mcp.tool()
def approval_reject(approval_id: str, approver: str = "store_manager", reason: str = "",
                    scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """审批驳回（pending -> rejected）：人工决策，标记关联订单 rollback_requested，
    由执行层显式调用 order_rollback 回滚（决策与执行分离）。对应 HTTP mock: mock_finance.reject。"""
    return _tools(scenario_id).reject(approval_id, approver, reason)


# ---- 试驾 ----
@mcp.tool()
def testdrive_list_slots(store_id: str, model_code: str, scenario_id: str = DEFAULT_SCENARIO) -> list:
    """查询试驾档期。对应 HTTP mock: mock_testdrive.list_slots。"""
    return _tools(scenario_id).list_slots(store_id, model_code)


@mcp.tool()
def testdrive_book_slot(customer_id: str, store_id: str, slot: str, model_code: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """预约试驾（L1 自动执行，可取消回滚）。对应 HTTP mock: mock_testdrive.book_slot。"""
    return _tools(scenario_id).book_slot(customer_id, store_id, slot, model_code)


# ---- 订单（幂等+审批+回滚）----
@mcp.tool()
def order_create(lead_id: str, quote_id: str, order_key: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """创建订单草稿（幂等：同 order_key 不重复创建；合同/交付 L2/L3 需审批）。对应 HTTP mock: mock_order.create_order。"""
    return _tools(scenario_id).create_order(lead_id, quote_id, order_key)


@mcp.tool()
def order_rollback(order_id: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """订单回滚到创建前状态（回滚点 draft，审计保留）。对应 HTTP mock: mock_order.rollback_order。"""
    return _tools(scenario_id).rollback_order(order_id)


@mcp.tool()
def order_confirm(order_id: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """订单 draft -> confirmed：门禁——所有关联审批必须已 approved 且无 rejected 才放行
    （高风险动作禁止默认放行）。对应 HTTP mock: mock_order.confirm_order。"""
    return _tools(scenario_id).confirm_order(order_id)


# ---- 知识库 RAG ----
@mcp.tool()
def knowledge_rag_search(query: str, kind: str = "sop", scenario_id: str = DEFAULT_SCENARIO) -> list:
    """RAG 检索：kind=product(产品知识)/sop(销售SOP)/case(成交案例)。对应 HTTP mock: mock_knowledge.search_*。

    失败处理：检索不到相关内容返回空列表（不编造），由 Agent 判断是否足以支撑决策。
    """
    t = _tools(scenario_id)
    if kind == "product":
        return t.search_product(query)
    if kind == "case":
        return t.search_case(query)
    return t.search_sop(query)


# ---- 闭环验证 ----
@mcp.tool()
def deal_verify(deal_id: str, scenario_id: str = DEFAULT_SCENARIO) -> dict:
    """成交闭环验证：汇总已执行动作/订单/审批状态，输出闭环结论。对应 HTTP mock: mock_verify.check_deal。"""
    return _tools(scenario_id).check_deal(deal_id)


@mcp.tool()
def audit_query(approval_id: str = "", order_id: str = "", scenario_id: str = DEFAULT_SCENARIO) -> list:
    """审计轨迹查询：按 approval_id / order_id 可选筛选，返回结构化 actions（含 action_id、
    name、risk_level、time、关联业务键），全量与 trace_id 关联，支持回放与审计。
    对应 HTTP mock: mock_verify.audit_trail / GET /tools/{sid}/audit。"""
    return _tools(scenario_id).audit_trail(approval_id or None, order_id or None)


if __name__ == "__main__":
    mcp.run()
