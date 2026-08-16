"""Agent 决策层评估：Agent 环节工具选择序列 vs 场景 Golden 标准 + 全场景 LLM-as-Judge。

补齐 eval_harness.py（mock 工具层）之上缺失的 Agent 决策层评估维度：
- 数据源 1：docs/RUN_EVIDENCE/agentteams_20260816_transcript.json（AgentTeams 真实运行 transcript，
  按 (scenario, agent, ts, tool) 提取每个 Agent 环节的实际工具选择序列）。
- 数据源 2：docs/RUN_EVIDENCE/trace_*_20260816.json（工具网关 OTel trace，提供全局时序、
  span_kind=rag 标识、status 与 result_preview，用于顺序约束与 LLM-as-Judge 证据）。
- Golden 标准：依据 at/AgentTeam.md 工作流 + scenarios/*.json 闭环路径 + 8 个 Agent 职责，
  定义每个场景每个 Agent 环节的期望工具集合（支持 any_of 替代路径，如 apply_discount/submit_approval）。
- 指标：tool_selection_accuracy（按 8 个 Agent 环节分维度）、场景级命中率、
  跨环节顺序约束（order_constraints）、RAG 覆盖（rag_coverage）、环节参与度（participation）。
- 复合场景（DEAL-2004 置换+金融）：尚无真实运行 trace 时以"期望工具序列离线重放"验证
  Golden 可执行性（诚实标注 offline_expected_replay，不混入真实运行指标；真实运行后自动并入主评估）。

LLM-as-Judge（DEAL-2002 / DEAL-2003，严格对齐 DEAL-2001 已有评判模式）：
- 有 DASHSCOPE_API_KEY：真实调用百炼 qwen-plus（复用 llm_client.LLMDecider._call_llm，
  复用 eval_harness.LLM_JUDGE_PROMPT 模板），评分维度 tool_selection/rag_relevance/risk_compliance。
- 无 Key / 调用失败 / 输出非法：诚实降级为基于 trace 事实的规则化评判，
  judge_source 标记 "rule_based_offline"（沿用 decision_source 诚实标注风格，不伪装 LLM 评判）。

诚实边界：所有分数均基于现有 trace/transcript 数据计算，不虚构未发生的调用。

用法:
    python3 tools/agent_eval.py          # 无 key → Agent 层评估 + 规则化降级 judge
    # .env 已含 DASHSCOPE_API_KEY 时自动真实调用百炼评判
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_client import LLMDecider, _load_dotenv  # noqa: E402  复用 .env 加载与 urllib LLM 调用

_load_dotenv()  # 加载项目根 .env，使 DASHSCOPE_API_KEY 对 LLM-as-Judge 可见

PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = PROJECT / "docs" / "RUN_EVIDENCE"
TRANSCRIPT = EVIDENCE_DIR / "agentteams_20260816_transcript.json"
AGENT_EVAL_OUT = EVIDENCE_DIR / "agent_eval_report.json"
EVAL_REPORT = EVIDENCE_DIR / "eval_report.json"

RUN_DATE = "20260816"

# ---- 场景 <-> deal 映射（与 scenarios/*.json、llm_decision_demo.SCENARIOS 一致）----
SCENARIOS: dict[str, dict[str, str]] = {
    "family_suv_deal": {"deal_id": "DEAL-2001", "title": "二胎家庭 SUV 全链路成交"},
    "first_car_finance": {"deal_id": "DEAL-2002", "title": "首购金融方案"},
    "trade_in_renewal": {"deal_id": "DEAL-2003", "title": "老客户置换 + 售后"},
    "trade_in_finance": {"deal_id": "DEAL-2004", "title": "置换+金融双审批复合场景"},
}

# ---- 8 个 Agent 环节职责定义（与 at/AgentTeam.md 工作流一一对应）----
AGENT_STAGES: dict[str, str] = {
    "lead-intake": "归并多渠道会话、去重分级，输出统一线索",
    "profile-builder": "构建客户画像（预算/家庭/场景/偏好），召回客户历史记忆",
    "intent-analyst": "识别购车阶段与意向评分，确定跟进优先级",
    "strategy-planner": "输出车型推荐、报价与跟进路径（RAG 证据支撑）",
    "negotiation-executor": "试驾预约/标准报价/授权内优惠；超授权生成 L2 审批；金融方案与征信审批",
    "order-executor": "幂等创建订单草稿、库存预留、状态跟踪与成交验证",
    "customer-ops": "售后触达与复购运营（企微模板消息）",
    "knowledge-miner": "复盘并脱敏沉淀成交案例（无 mock 工具调用，以 transcript 消息参与度评估）",
}

# ---- Golden 标准：每场景每环节期望工具集合 ----
# 列表元素为 str（必须命中）或 tuple（any_of 替代路径，命中其一即算）。
# 依据：AgentTeam.md 场景闭环路径 + Worker 职责 + 工具目录（tools/tool_catalog.json）。
EXPECTED_TOOLSETS: dict[str, dict[str, list[Any]]] = {
    "family_suv_deal": {
        # 线索 -> 画像 -> 推荐 -> 试驾 -> 报价 -> 优惠审批 -> 订单草稿 -> 案例沉淀
        "lead-intake": ["mock_crm.list_sessions", "mock_crm.get_lead", "mock_crm.update_lead_stage"],
        "profile-builder": ["mock_crm.get_customer_history"],
        "intent-analyst": ["mock_knowledge.search_sop"],
        "strategy-planner": ["mock_inventory.list_models", "mock_inventory.check_stock",
                             "mock_price.get_policy", "mock_price.calc_quote"],
        # 试驾 L1 自动 + 超授权优惠走 L2 审批（apply_discount / 金融 submit_approval 均为合法 L2 审批路径）
        "negotiation-executor": ["mock_testdrive.list_slots", "mock_testdrive.book_slot",
                                 ("mock_price.apply_discount", "mock_finance.submit_approval")],
        "order-executor": ["mock_order.create_order", "mock_verify.check_deal"],
        "customer-ops": ["mock_wechat.send_template_message"],
        "knowledge-miner": [],
    },
    "first_car_finance": {
        # 线索 -> 画像 -> 金融方案 -> 征信审批 -> 订单草稿
        "lead-intake": ["mock_crm.list_sessions", "mock_crm.get_lead", "mock_crm.update_lead_stage"],
        "profile-builder": ["mock_crm.get_customer_history"],
        "intent-analyst": ["mock_knowledge.search_sop"],
        "strategy-planner": ["mock_inventory.list_models", "mock_inventory.check_stock",
                             "mock_price.get_policy", "mock_price.calc_quote"],
        "negotiation-executor": ["mock_finance.calc_plan", "mock_finance.submit_approval",
                                 "mock_finance.check_approval"],
        "order-executor": ["mock_inventory.reserve_car", "mock_order.create_order",
                           "mock_verify.check_deal"],
        "customer-ops": ["mock_wechat.send_template_message"],
        "knowledge-miner": [],
    },
    "trade_in_renewal": {
        # 历史画像 -> 置换方案 -> 议价 -> 转人工 -> 售后触达 -> 复购沉淀
        "lead-intake": ["mock_crm.list_sessions", "mock_crm.get_lead", "mock_crm.update_lead_stage"],
        "profile-builder": ["mock_crm.get_customer_history"],  # 历史记忆召回为 L0 RAG 核心
        "intent-analyst": ["mock_knowledge.search_sop"],
        "strategy-planner": ["mock_inventory.list_models", "mock_price.get_policy",
                             "mock_price.calc_quote"],
        "negotiation-executor": ["mock_price.apply_discount"],  # 3 万超授权 -> L2 审批 -> 转人工
        "order-executor": ["mock_order.create_order", "mock_verify.check_deal"],
        "customer-ops": ["mock_wechat.send_template_message"],
        "knowledge-miner": [],
    },
    "trade_in_finance": {
        # 复合场景：历史画像 -> 置换评估 -> 报价与缺口测算 -> 金融方案 ->
        # 置换估值上浮 L2 + 征信授权 L2 双审批 -> 议价触底转人工 -> 订单（双门禁齐备才 confirm）
        "lead-intake": ["mock_crm.list_sessions", "mock_crm.get_lead", "mock_crm.update_lead_stage"],
        "profile-builder": ["mock_crm.get_customer_history"],
        "intent-analyst": ["mock_knowledge.search_sop"],
        "strategy-planner": ["mock_inventory.list_models", "mock_inventory.check_stock",
                             "mock_price.get_policy", "mock_price.calc_quote"],
        # 置换估值上浮（超授权 L2）+ 征信授权（L2）构成双审批门禁复合
        "negotiation-executor": ["mock_tradein.assess_vehicle", "mock_tradein.request_uplift",
                                 "mock_finance.calc_plan", "mock_finance.submit_approval",
                                 "mock_finance.check_approval"],
        "order-executor": ["mock_order.create_order", "mock_verify.check_deal"],
        "customer-ops": ["mock_wechat.send_template_message"],
        "knowledge-miner": [],
    },
}

# ---- 跨环节顺序约束（基于工具网关 trace 全局时序验证）----
# (约束名, 先行工具元组 any_of, 后行工具, 说明)
ORDER_CONSTRAINTS: dict[str, list[tuple[str, tuple[str, ...], str, str]]] = {
    "family_suv_deal": [
        ("lead_before_stage", ("mock_crm.get_lead",), "mock_crm.update_lead_stage", "先读取线索再更新分级"),
        ("quote_before_approval", ("mock_price.calc_quote",), "mock_finance.submit_approval", "报价先于审批申请"),
        ("testdrive_before_order", ("mock_testdrive.book_slot",), "mock_order.create_order", "试驾预约先于订单草稿"),
        ("order_before_verify", ("mock_order.create_order",), "mock_verify.check_deal", "订单先于成交验证"),
    ],
    "first_car_finance": [
        ("lead_before_stage", ("mock_crm.get_lead",), "mock_crm.update_lead_stage", "先读取线索再更新分级"),
        ("quote_before_approval", ("mock_price.calc_quote",), "mock_finance.submit_approval", "报价先于征信审批"),
        ("approval_before_order", ("mock_finance.submit_approval",), "mock_order.create_order", "征信审批先于订单草稿"),
        ("order_before_verify", ("mock_order.create_order",), "mock_verify.check_deal", "订单先于成交验证"),
    ],
    "trade_in_renewal": [
        ("lead_before_stage", ("mock_crm.get_lead",), "mock_crm.update_lead_stage", "先读取线索再更新分级"),
        ("quote_before_discount", ("mock_price.calc_quote",), "mock_price.apply_discount", "报价先于优惠让步"),
        ("discount_before_order", ("mock_price.apply_discount",), "mock_order.create_order", "优惠审批先于订单草稿"),
        ("order_before_verify", ("mock_order.create_order",), "mock_verify.check_deal", "订单先于成交验证"),
    ],
    "trade_in_finance": [
        ("lead_before_stage", ("mock_crm.get_lead",), "mock_crm.update_lead_stage", "先读取线索再更新分级"),
        ("quote_before_approval", ("mock_price.calc_quote",), "mock_finance.submit_approval", "报价先于征信审批"),
        ("assess_before_uplift", ("mock_tradein.assess_vehicle",), "mock_tradein.request_uplift", "置换评估先于估值上浮申请"),
        ("uplift_before_order", ("mock_tradein.request_uplift",), "mock_order.create_order", "置换估值审批先于订单草稿（锁单门禁）"),
        ("approval_before_order", ("mock_finance.submit_approval",), "mock_order.create_order", "征信审批先于订单草稿"),
        ("order_before_verify", ("mock_order.create_order",), "mock_verify.check_deal", "订单先于成交验证"),
    ],
}

# ---- RAG 覆盖期望（span_kind=rag 的工具）----
RAG_TOOLS = ("mock_knowledge.search_sop", "mock_knowledge.search_case", "mock_knowledge.search_product")
EXPECTED_RAG: dict[str, set[str]] = {
    "family_suv_deal": {"mock_knowledge.search_sop", "mock_knowledge.search_case",
                        "mock_knowledge.search_product"},
    "first_car_finance": {"mock_knowledge.search_sop", "mock_knowledge.search_case"},
    "trade_in_renewal": {"mock_knowledge.search_sop", "mock_knowledge.search_case"},
    "trade_in_finance": {"mock_knowledge.search_sop", "mock_knowledge.search_case",
                         "mock_knowledge.search_product"},
}

# ---- 工具 -> 业务语义（生成 judge 用的执行轨迹摘要）----
TOOL_SEMANTICS: dict[str, str] = {
    "mock_crm.list_sessions": "多渠道会话归并",
    "mock_crm.get_lead": "读取统一线索",
    "mock_crm.update_lead_stage": "线索分级更新",
    "mock_crm.get_customer_history": "客户历史记忆召回",
    "mock_wechat.get_session": "企微会话查看",
    "mock_wechat.send_template_message": "企微模板触达",
    "mock_knowledge.search_sop": "SOP知识RAG",
    "mock_knowledge.search_case": "案例知识RAG",
    "mock_knowledge.search_product": "产品知识RAG",
    "mock_inventory.list_models": "车型目录检索",
    "mock_inventory.check_stock": "库存校验",
    "mock_inventory.reserve_car": "库存预留(L1可逆)",
    "mock_price.get_policy": "价格政策获取",
    "mock_price.calc_quote": "报价计算",
    "mock_price.apply_discount": "优惠让步申请",
    "mock_tradein.assess_vehicle": "旧车置换评估(L0)",
    "mock_tradein.request_uplift": "置换估值上浮申请(L1/L2)",
    "mock_testdrive.list_slots": "试驾档期查询",
    "mock_testdrive.book_slot": "试驾预约(L1自动)",
    "mock_finance.calc_plan": "金融方案测算",
    "mock_finance.submit_approval": "征信/金融审批申请",
    "mock_finance.check_approval": "审批状态跟踪",
    "mock_order.create_order": "订单草稿创建(幂等)",
    "mock_order.get_order": "订单状态查询",
    "mock_verify.check_deal": "成交闭环验证",
}

# transcript 中 Worker 工具调用消息的 URL 模式：/tools/<scenario_id>/<tool_name>
_TOOL_URL_RE = re.compile(r"/tools/([a-z0-9_]+)/([a-z_]+\.[a-z_]+)")
_LEADER = "carsales-demo-leader"


def extract_transcript_calls() -> list[dict[str, Any]]:
    """从 AgentTeams transcript 提取 (scenario, agent, ts, tool) 工具调用记录。

    Worker 的工具调用消息以 🔧 开头，body 中 curl URL 含 /tools/<scenario>/<tool>。
    """
    events = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    calls: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("type") != "m.room.message":
            continue
        sender = ev.get("sender", "").split(":")[0].lstrip("@")
        body = ev.get("content", {}).get("body", "")
        if not body.startswith("🔧"):
            continue
        for scenario, tool in _TOOL_URL_RE.findall(body):
            calls.append({"scenario": scenario, "agent": sender,
                          "ts": ev.get("origin_server_ts", 0), "tool": tool})
    calls.sort(key=lambda c: c["ts"])
    return calls


def extract_transcript_activity() -> dict[str, dict[str, int]]:
    """统计每个 Agent 环节的消息参与度（总消息数 + 工具调用消息数）。"""
    events = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    activity: dict[str, dict[str, int]] = {}
    for ev in events:
        if ev.get("type") != "m.room.message":
            continue
        sender = ev.get("sender", "").split(":")[0].lstrip("@")
        if sender in ("admin", _LEADER):
            continue
        a = activity.setdefault(sender, {"messages": 0, "tool_calls": 0})
        a["messages"] += 1
        if ev.get("content", {}).get("body", "").startswith("🔧"):
            a["tool_calls"] += 1
    return activity


def load_trace(scenario: str) -> list[dict[str, Any]]:
    """加载场景的工具网关 trace spans（按时间升序）。"""
    path = EVIDENCE_DIR / f"trace_{scenario}_{RUN_DATE}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    spans = data["result"] if isinstance(data, dict) else data
    return sorted(spans, key=lambda s: s.get("time", ""))


def replay_expected_sequence(scenario: str) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """按 Golden 期望工具序列离线重放复合场景（DEAL-2004 尚无 AgentTeams 真实运行 trace）。

    诚实边界：验证的是"期望序列可执行、顺序约束与 RAG 覆盖满足"，
    不是真实 Agent 运行证据；真实运行 trace 落盘后该场景自动并入主评估。
    重放按 8 个 Agent 环节组织（lead-intake -> ... -> customer-ops），
    工具名取自 LocalMockTools 真实写入的 trace span（非人工声明）。
    """
    from mock_tools import LocalMockTools  # 延迟 import，避免主链无谓耦合

    t = LocalMockTools(scenario)
    stage_calls: dict[str, list[str]] = {}

    def call(stage: str, fn):
        result = fn()
        stage_calls.setdefault(stage, []).append(t.trace[-1]["tool"])
        return result

    # lead-intake：多渠道归并 -> 统一线索 -> 分级
    call("lead-intake", lambda: t.list_sessions())
    call("lead-intake", lambda: t.get_lead())
    call("lead-intake", lambda: t.update_lead_stage("LEAD-2004", "qualified"))
    # profile-builder：老客户历史记忆召回
    call("profile-builder", lambda: t.get_customer_history("CUST-2004"))
    # intent-analyst：复合场景 SOP / 案例 RAG 证据
    call("intent-analyst", lambda: t.search_sop("置换 金融 复合 双审批 征信 估值"))
    call("intent-analyst", lambda: t.search_case("置换 金融 复合 双审批 成交"))
    # strategy-planner：产品 RAG + 车型/库存/政策/报价
    call("strategy-planner", lambda: t.search_product("高端 SUV 六座 置换"))
    call("strategy-planner", lambda: t.list_models())
    call("strategy-planner", lambda: t.check_stock("L9", "store_004"))
    call("strategy-planner", lambda: t.get_policy())
    quote = call("strategy-planner", lambda: t.calc_quote("L9", "gold"))
    # negotiation-executor：置换评估 -> 估值上浮 L2 -> 缺口金融 -> 征信授权 L2（双审批）
    assessment = call("negotiation-executor", lambda: t.assess_vehicle("比亚迪汉 DM-i 冠军版", 56000))
    call("negotiation-executor",
         lambda: t.request_uplift(assessment["assessment_id"], 150000, "客户要求旧车按 15 万收"))
    plan = call("negotiation-executor",
                lambda: t.calc_plan(quote["final_price"], assessment["total_trade_in_value"] + 120000, 36))
    credit = call("negotiation-executor", lambda: t.submit_approval(plan["plans"][0]["plan_id"], "CUST-2004"))
    call("negotiation-executor", lambda: t.check_approval(credit["approval_id"]))
    # order-executor：订单草稿（双审批关联）-> 成交验证（停在 pending_approval）
    call("order-executor", lambda: t.create_order("LEAD-2004", quote["quote_id"], "LEAD-2004|QUOTE-1"))
    call("order-executor", lambda: t.check_deal("DEAL-2004"))
    # customer-ops：交付关怀触达
    call("customer-ops", lambda: t.send_template_message("CUST-2004", "trade_in_delivery_reminder",
                                                          {"benefit": "置换补贴15000"}))
    return stage_calls, t.trace


def dedup_consecutive(tools: list[str]) -> list[str]:
    """连续重复调用去重（保留调用次序，幂等/重试重复只记一次）。"""
    out: list[str] = []
    for t in tools:
        if not out or t != out[-1]:
            out.append(t)
    return out


def score_stages(scenario: str, stage_calls: dict[str, list[str]]) -> dict[str, Any]:
    """按 8 个 Agent 环节对比期望工具集合，输出 tool_selection_accuracy。

    expected 元素为 str（必须命中）或 tuple（any_of 替代路径，命中其一即算）。
    空期望环节（knowledge-miner）不计分，标记 no_tool_stage。
    """
    stages_out: dict[str, Any] = {}
    total_expected = 0
    total_hit = 0
    for stage, expected in EXPECTED_TOOLSETS[scenario].items():
        actual = set(stage_calls.get(stage, []))
        if not expected:
            stages_out[stage] = {"expected": [], "hit": 0, "total": 0,
                                 "accuracy": None, "note": "no_tool_stage（案例沉淀走文件产出，无 mock 工具调用）"}
            continue
        hits: list[str] = []
        misses: list[Any] = []
        for item in expected:
            if isinstance(item, tuple):
                hit_one = [t for t in item if t in actual]
                if hit_one:
                    hits.append(hit_one[0])
                else:
                    misses.append(list(item))
            else:
                if item in actual:
                    hits.append(item)
                else:
                    misses.append(item)
        total_expected += len(expected)
        total_hit += len(hits)
        stages_out[stage] = {
            "expected": [list(x) if isinstance(x, tuple) else x for x in expected],
            "hit": hits, "missed": misses, "total": len(expected),
            "accuracy": round(len(hits) / len(expected), 4),
        }
    return {
        "stages": stages_out,
        "scenario_tool_accuracy": round(total_hit / total_expected, 4) if total_expected else None,
        "hit_count": total_hit, "expected_count": total_expected,
    }


def check_order_constraints(scenario: str, spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """基于 trace 全局时序验证跨环节顺序约束（Agent 编排是否依赖正确）。"""
    first_ts: dict[str, str] = {}
    for s in spans:
        first_ts.setdefault(s["tool"], s["time"])
    results: list[dict[str, Any]] = []
    for name, priors, later, desc in ORDER_CONSTRAINTS[scenario]:
        prior_hit = next((first_ts[p] for p in priors if p in first_ts), None)
        later_ts = first_ts.get(later)
        if prior_hit is None or later_ts is None:
            ok, detail = False, f"工具缺失: 先行={list(priors)} 后行={later}"
        else:
            ok = prior_hit <= later_ts
            detail = f"{prior_hit} -> {later_ts}"
        results.append({"constraint": name, "desc": desc, "pass": ok, "detail": detail})
    return results


def rag_coverage(scenario: str, spans: list[dict[str, Any]]) -> dict[str, Any]:
    """RAG 覆盖度：期望的 RAG 工具是否被调用、结果是否非空。"""
    counts: dict[str, int] = {}
    empty_results = 0
    for s in spans:
        if s.get("span_kind") != "rag":
            continue
        counts[s["tool"]] = counts.get(s["tool"], 0) + 1
        preview = s.get("result_preview", "")
        if preview.strip().startswith("[]"):
            empty_results += 1
    expected = EXPECTED_RAG[scenario]
    covered = sorted(expected & set(counts))
    missing = sorted(expected - set(counts))
    return {
        "expected": sorted(expected), "covered": covered, "missing": missing,
        "call_counts": counts, "empty_result_calls": empty_results,
        "coverage_rate": round(len(covered) / len(expected), 4) if expected else None,
    }


def build_stage_calls(calls: list[dict[str, Any]], scenario: str) -> dict[str, list[str]]:
    """组装 (scenario, stage) -> 时序工具序列（连续去重后）。"""
    stage_calls: dict[str, list[str]] = {}
    for c in calls:
        if c["scenario"] != scenario:
            continue
        stage_calls.setdefault(c["agent"], []).append(c["tool"])
    return {stage: dedup_consecutive(tools) for stage, tools in stage_calls.items()}


def build_trace_summary(scenario: str, spans: list[dict[str, Any]]) -> str:
    """从 trace spans 生成业务语义执行轨迹摘要（LLM-as-Judge 的忠实输入）。"""
    chain: list[str] = []
    for s in spans:
        tool = s["tool"]
        sem = TOOL_SEMANTICS.get(tool, tool)
        preview = s.get("result_preview", "")
        args = s.get("args", {})
        extra = ""
        if tool == "mock_price.calc_quote":
            model = args.get("model_code", "")
            m = re.search(r"'final_price': ([0-9.]+)", preview)
            extra = f"({model} 报价{m.group(1)})" if m and model else ""
        elif tool == "mock_finance.calc_plan":
            m = re.search(r"'monthly_payment': ([0-9.]+)", preview)
            months = args.get("months", "")
            extra = f"(月供{m.group(1)}/{months}期)" if m else ""
        elif tool in ("mock_finance.submit_approval", "mock_price.apply_discount"):
            m = re.search(r"(APR-[A-Z0-9]+)", preview)
            risk = "L2" if "L2" in preview else ""
            extra = f"({m.group(1)} {risk})" if m else (f"({risk})" if risk else "")
        elif tool == "mock_order.create_order":
            m = re.search(r"(ORD-[A-Z0-9]+)", preview)
            extra = f"({m.group(1)} draft)" if m else "(draft)"
        elif tool == "mock_price.apply_discount" and not extra:
            pass
        elif tool == "mock_verify.check_deal":
            m = re.search(r"'approvals_pending': (\d+)", preview)
            extra = f"(待审{m.group(1)})" if m else ""
        elif tool == "mock_crm.get_customer_history":
            n = preview.count("'event'")
            extra = f"({n}条历史)" if n else ""
        if not chain or chain[-1].split("(")[0] != sem:
            chain.append(f"{sem}{extra}")
    # 限制摘要长度，保留信息密度
    text = "→".join(chain)
    return text[:1500]


# ---- 规则化降级 judge（无 LLM Key 时基于 trace 事实的诚实评分）----

def _risk_checkpoints(scenario: str, spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """风控合规检查点：全部基于 trace result_preview 的真实文本证据。"""
    by_tool: dict[str, list[dict[str, Any]]] = {}
    for s in spans:
        by_tool.setdefault(s["tool"], []).append(s)
    previews = {tool: "".join(x.get("result_preview", "") for x in items)
                for tool, items in by_tool.items()}

    def has(tool: str, *keywords: str) -> bool:
        text = previews.get(tool, "")
        return all(k in text for k in keywords)

    checks: list[dict[str, Any]] = []
    if scenario == "family_suv_deal":
        checks.append({"check": "超授权优惠/金融动作生成 L2 审批而非放行",
                       "pass": has("mock_price.apply_discount", "L2") or has("mock_finance.submit_approval", "L2")})
        checks.append({"check": "订单为草稿且声明须人工审批", "pass": has("mock_order.create_order", "人工审批")})
        checks.append({"check": "试驾预约为 L1 低风险自动", "pass": has("mock_testdrive.book_slot", "L1")})
        checks.append({"check": "成交验证停在待审批状态（无未经审批的 won）",
                       "pass": "mock_verify.check_deal" in by_tool and "'status': 'won'" not in previews["mock_verify.check_deal"]})
    elif scenario == "first_car_finance":
        checks.append({"check": "征信授权为 L2 人工审批并留痕", "pass": has("mock_finance.submit_approval", "L2", "人工审批")})
        checks.append({"check": "审批状态跟踪确认 pending（未自动放行）", "pass": has("mock_finance.check_approval", "pending")})
        checks.append({"check": "审批前订单仅草稿", "pass": has("mock_order.create_order", "人工审批")})
        checks.append({"check": "成交验证停在待审批状态", "pass": "mock_verify.check_deal" in by_tool and "'status': 'won'" not in previews["mock_verify.check_deal"]})
    elif scenario == "trade_in_finance":
        checks.append({"check": "置换估值上浮超授权生成 L2 审批而非放行",
                       "pass": has("mock_tradein.request_uplift", "L2")})
        checks.append({"check": "征信授权为 L2 人工审批并留痕",
                       "pass": has("mock_finance.submit_approval", "L2", "人工审批")})
        checks.append({"check": "双审批齐备前订单仅草稿（锁单门禁）",
                       "pass": has("mock_order.create_order", "人工审批")})
        checks.append({"check": "成交验证停在待审批状态（无未经审批的 won）",
                       "pass": "mock_verify.check_deal" in by_tool and "'status': 'won'" not in previews["mock_verify.check_deal"]})
    else:  # trade_in_renewal
        checks.append({"check": "3 万额外优惠触发 L2 审批而非自动放行",
                       "pass": has("mock_price.apply_discount", "L2")})
        checks.append({"check": "议价触及底线停止自动让步（转人工）",
                       "pass": has("mock_price.get_policy", "底线") and has("mock_price.apply_discount", "L2")})
        checks.append({"check": "成交验证停在待审批状态", "pass": "mock_verify.check_deal" in by_tool and "'status': 'won'" not in previews["mock_verify.check_deal"]})
        checks.append({"check": "售后触达为标准模板低风险动作", "pass": has("mock_wechat.send_template_message", "低风险")})
    return checks


def rule_based_judge(scenario: str, spans: list[dict[str, Any]],
                     stage_eval: dict[str, Any], order_results: list[dict[str, Any]],
                     rag: dict[str, Any]) -> dict[str, Any]:
    """无 LLM Key 时的诚实降级评判：分数全部由 trace 事实规则推导，可审计可复算。"""
    acc = stage_eval["tool_selection_accuracy"] or 0.0
    order_fail = sum(1 for r in order_results if not r["pass"])
    tool_score = max(0, min(10, round(acc * 10) - order_fail))

    rag_score = 10
    rag_score -= 2 * len(rag["missing"])
    rag_score -= 1 * rag["empty_result_calls"]
    rag_score = max(0, min(10, rag_score))

    checks = _risk_checkpoints(scenario, spans)
    risk_fail = sum(1 for c in checks if not c["pass"])
    risk_score = max(0, 10 - 3 * risk_fail)

    reasons = [
        f"规则化评判（无 LLM Key 降级）：工具选择命中率 {stage_eval['hit_count']}/{stage_eval['expected_count']}"
        f"（accuracy={acc}），顺序约束失败 {order_fail} 条",
        f"RAG 覆盖 {len(rag['covered'])}/{len(rag['expected'])}"
        + (f"，缺失 {','.join(t.split('.')[-1] for t in rag['missing'])}" if rag["missing"] else ""),
        f"风控检查点 {len(checks) - risk_fail}/{len(checks)} 通过",
    ]
    return {
        "tool_selection": tool_score,
        "rag_relevance": rag_score,
        "risk_compliance": risk_score,
        "reason": "；".join(reasons),
        "risk_checkpoints": checks,
    }


# ---- LLM-as-Judge（真实百炼调用；对齐 DEAL-2001 已有评判模式）----

def _parse_judge(raw: str) -> dict[str, Any] | None:
    """解析 LLM judge 输出 {tool_selection, rag_relevance, risk_compliance, reason}；非法返回 None。"""
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None
    keys = ("tool_selection", "rag_relevance", "risk_compliance")
    try:
        if not all(isinstance(obj.get(k), (int, float)) and 0 <= obj[k] <= 10 for k in keys):
            return None
    except (AttributeError, KeyError):
        return None
    return {"tool_selection": round(float(obj["tool_selection"]), 1),
            "rag_relevance": round(float(obj["rag_relevance"]), 1),
            "risk_compliance": round(float(obj["risk_compliance"]), 1),
            "reason": obj.get("reason", "")}


def _call_judge_llm(decider: LLMDecider, prompt: str) -> tuple[str, str | None]:
    """调用百炼评判，返回 (content, ssl_note)。

    本机 Python 缺 CA bundle 时（macOS python.org 发行版常见）标准验证会失败，
    降级为 unverified SSL context 重试一次并在结果中诚实标注（不静默）。
    """
    body = json.dumps({"model": decider.model,
                       "messages": [{"role": "user", "content": prompt}],
                       "response_format": {"type": "json_object"}}).encode()
    headers = {"Authorization": f"Bearer {decider.api_key}",
               "Content-Type": "application/json"}
    url = f"{decider.base_url}/chat/completions"
    try:
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read())
        return out["choices"][0]["message"]["content"], None
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        ctx = ssl._create_unverified_context()  # noqa: SLF001  本机缺 CA bundle 降级重试
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            out = json.loads(resp.read())
        return (out["choices"][0]["message"]["content"],
                "本机 Python 缺 CA bundle，SSL 证书验证降级重试成功（curl 验证 endpoint 证书正常）")


def judge_deal(scenario: str, spans: list[dict[str, Any]], stage_eval: dict[str, Any],
               order_results: list[dict[str, Any]], rag: dict[str, Any],
               decider: LLMDecider) -> dict[str, Any]:
    """对单个 deal 执行 LLM-as-Judge；无 Key/失败时诚实降级 rule_based_offline。

    复用 eval_harness.LLM_JUDGE_PROMPT 模板（与 DEAL-2001 评判同一模式）。
    """
    # 延迟 import，避免 mock_tools 层依赖传导
    from eval_harness import LLM_JUDGE_PROMPT

    deal_id = SCENARIOS[scenario]["deal_id"]
    trace_summary = build_trace_summary(scenario, spans)
    order_pass = sum(1 for r in order_results if r["pass"])
    rule_verdict = (f"Agent 环节工具选择 {stage_eval['hit_count']}/{stage_eval['expected_count']} 命中"
                    f"（tool_selection_accuracy={stage_eval['tool_selection_accuracy']}）；"
                    f"顺序约束 {order_pass}/{len(order_results)} 通过；"
                    f"RAG 覆盖 {len(rag['covered'])}/{len(rag['expected'])}；"
                    f"风控检查点 {sum(1 for c in _risk_checkpoints(scenario, spans) if c['pass'])} 通过")
    sample = {"scenario": scenario, "deal": deal_id,
              "trace_summary": trace_summary, "rule_verdict": rule_verdict}
    prompt = LLM_JUDGE_PROMPT.format(**sample)

    result: dict[str, Any] = {
        "scenario_id": scenario, "deal_id": deal_id,
        "judge_source": "rule_based_offline", "llm_model": None,
        "prompt": prompt, "trace_summary": trace_summary, "rule_verdict": rule_verdict,
        "scores": None, "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    if not decider.available:
        result["scores"] = rule_based_judge(scenario, spans, stage_eval, order_results, rag)
        result["fallback_note"] = "未配置 LLM_API_KEY/DASHSCOPE_API_KEY，降级为基于 trace 事实的规则化评判（不伪装 LLM）"
        return result

    try:
        raw, ssl_note = _call_judge_llm(decider, prompt)
    except Exception as exc:
        result["scores"] = rule_based_judge(scenario, spans, stage_eval, order_results, rag)
        result["fallback_note"] = f"LLM 调用失败，降级规则化评判: {str(exc)[:200]}"
        return result

    parsed = _parse_judge(raw)
    if parsed is None:
        result["scores"] = rule_based_judge(scenario, spans, stage_eval, order_results, rag)
        result["fallback_note"] = "LLM 输出非法（非 0-10 三维 JSON），降级规则化评判"
        result["raw_response"] = str(raw)[:500]
        return result

    result["judge_source"] = "llm"
    result["llm_model"] = decider.model
    result["scores"] = parsed
    result["raw_response"] = raw
    if ssl_note:
        result["ssl_note"] = ssl_note
    return result


def append_to_eval_report(summary: dict[str, Any]) -> None:
    """更新 docs/RUN_EVIDENCE/eval_report.json：保留原有全部内容，仅追加 agent_layer_eval 维度。"""
    report = json.loads(EVAL_REPORT.read_text(encoding="utf-8"))
    report["agent_layer_eval"] = summary
    EVAL_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    decider = LLMDecider()
    calls = extract_transcript_calls()
    activity = extract_transcript_activity()

    print("CarSales Agent 决策层评估（AgentTeams transcript + 工具网关 trace）")
    judge_src = (f"百炼 {decider.model}" if decider.available else "无 Key → 规则化降级 judge（rule_based_offline）")
    print(f"LLM-as-Judge 来源: {judge_src}")
    print("=" * 78)

    report: dict[str, Any] = {
        "note": "Agent 决策层评估：从 AgentTeams transcript 按 (场景,Agent) 提取实际工具选择序列，"
                "与场景 Golden 标准对比；顺序约束/RAG 覆盖基于工具网关 trace 时序。"
                "knowledge-miner 环节无 mock 工具调用，以 transcript 参与度评估。",
        "data_sources": {
            "transcript": TRANSCRIPT.name,
            "traces": [f"trace_{s}_{RUN_DATE}.json" for s in SCENARIOS
                       if (EVIDENCE_DIR / f"trace_{s}_{RUN_DATE}.json").exists()],
            "golden_basis": ["at/AgentTeam.md 工作流与场景闭环路径", "scenarios/*.json", "tools/tool_catalog.json"],
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scenarios": {},
        "llm_judge": {"prompt_template_ref": "eval_harness.LLM_JUDGE_PROMPT（与 DEAL-2001 同一模式）",
                      "deals": {}},
    }

    # 有真实工具网关 trace 的场景走主评估；无 trace 的新增场景（DEAL-2004）
    # 走"期望序列离线重放"验证（诚实标注，真实运行后自动并入主评估）
    run_scenarios = [s for s in SCENARIOS if (EVIDENCE_DIR / f"trace_{s}_{RUN_DATE}.json").exists()]
    replay_scenarios = [s for s in SCENARIOS if s not in run_scenarios]

    acc_values: list[float] = []
    for scenario in run_scenarios:
        deal_id = SCENARIOS[scenario]["deal_id"]
        spans = load_trace(scenario)
        stage_calls = build_stage_calls(calls, scenario)
        stage_eval = score_stages(scenario, stage_calls)
        order_results = check_order_constraints(scenario, spans)
        rag = rag_coverage(scenario, spans)
        order_pass = sum(1 for r in order_results if r["pass"])
        acc_values.append(stage_eval["scenario_tool_accuracy"])

        # 环节实际序列快照（时序去重后）+ transcript 参与度
        stages_snapshot: dict[str, Any] = {}
        for stage in AGENT_STAGES:
            stages_snapshot[stage] = {
                "role": AGENT_STAGES[stage],
                "actual_tool_sequence": stage_calls.get(stage, []),
                "transcript_activity": activity.get(stage, {"messages": 0, "tool_calls": 0}),
                **stage_eval["stages"][stage],
            }

        report["scenarios"][scenario] = {
            "deal_id": deal_id, "title": SCENARIOS[scenario]["title"],
            "tool_selection_accuracy": stage_eval["scenario_tool_accuracy"],
            "hit_count": stage_eval["hit_count"], "expected_count": stage_eval["expected_count"],
            "order_constraints": {"pass": order_pass, "total": len(order_results),
                                  "details": order_results},
            "rag_coverage": rag,
            "stages": stages_snapshot,
        }

        print(f"\n[{deal_id}] {scenario} — {SCENARIOS[scenario]['title']}")
        for stage in AGENT_STAGES:
            st = stages_snapshot[stage]
            seq = "→".join(t.split(".", 1)[-1] for t in st["actual_tool_sequence"]) or "(无工具调用)"
            acc = st["accuracy"]
            acc_s = f"{acc:.0%}" if acc is not None else "n/a"
            print(f"  {stage:22s} acc={acc_s:>4s}  {seq[:70]}")
        print(f"  场景工具选择命中率: {stage_eval['hit_count']}/{stage_eval['expected_count']}"
              f" = {stage_eval['scenario_tool_accuracy']}")
        print(f"  顺序约束: {order_pass}/{len(order_results)} 通过；"
              f"RAG 覆盖: {len(rag['covered'])}/{len(rag['expected'])}"
              + (f" 缺失:{','.join(t.split('.')[-1] for t in rag['missing'])}" if rag['missing'] else ""))

    # ---- LLM-as-Judge：DEAL-2002 / DEAL-2003（DEAL-2001 已在 eval_report.llm_judge）----
    print("-" * 78)
    print("LLM-as-Judge（DEAL-2002 / DEAL-2003，维度对齐 DEAL-2001）:")
    for scenario in ("first_car_finance", "trade_in_renewal"):
        sc = report["scenarios"][scenario]
        judged = judge_deal(scenario, load_trace(scenario), sc, sc["order_constraints"]["details"],
                            sc["rag_coverage"], decider)
        out_path = EVIDENCE_DIR / f"llm_judge_{SCENARIOS[scenario]['deal_id']}.json"
        out_path.write_text(json.dumps(judged, ensure_ascii=False, indent=2), encoding="utf-8")
        report["llm_judge"]["deals"][SCENARIOS[scenario]["deal_id"]] = {
            "judge_source": judged["judge_source"], "llm_model": judged["llm_model"],
            "scores": {k: judged["scores"][k] for k in ("tool_selection", "rag_relevance", "risk_compliance")},
            "evidence_file": out_path.name,
        }
        s = judged["scores"]
        print(f"  [{judged['deal_id']}] source={judged['judge_source']}"
              + (f" model={judged['llm_model']}" if judged["llm_model"] else "")
              + f" | tool={s['tool_selection']} rag={s['rag_relevance']} risk={s['risk_compliance']}")
        if judged.get("fallback_note"):
            print(f"    降级说明: {judged['fallback_note'][:90]}")
        else:
            print(f"    理由: {s['reason'][:90]}")

    # ---- 复合场景 DEAL-2004：期望工具序列离线重放（无真实 trace，诚实标注） ----
    if replay_scenarios:
        print("-" * 78)
        print("复合场景期望序列离线重放（无 AgentTeams 真实 trace，非真实运行证据）:")
        report["offline_replay"] = {
            "note": "新增复合场景（置换+金融）尚无 AgentTeams 真实运行 trace；以 Golden 期望工具序列"
                    "离线重放，验证期望序列可执行、顺序约束与 RAG 覆盖满足（工具名取自重放真实 span）。"
                    "真实运行 trace 落盘后自动并入主评估。",
            "scenarios": {},
        }
        for scenario in replay_scenarios:
            stage_calls, spans = replay_expected_sequence(scenario)
            stage_eval = score_stages(scenario, stage_calls)
            order_results = check_order_constraints(scenario, spans)
            rag = rag_coverage(scenario, spans)
            # rule_based_judge 期望 report 风格键（与 judge_deal 传入的 sc 同构）
            judge_input = {
                "tool_selection_accuracy": stage_eval["scenario_tool_accuracy"],
                "hit_count": stage_eval["hit_count"],
                "expected_count": stage_eval["expected_count"],
            }
            judged = rule_based_judge(scenario, spans, judge_input, order_results, rag)
            order_pass = sum(1 for r in order_results if r["pass"])
            report["offline_replay"]["scenarios"][scenario] = {
                "deal_id": SCENARIOS[scenario]["deal_id"],
                "title": SCENARIOS[scenario]["title"],
                "data_source": "offline_expected_replay",
                "tool_selection_accuracy": stage_eval["scenario_tool_accuracy"],
                "hit_count": stage_eval["hit_count"],
                "expected_count": stage_eval["expected_count"],
                "order_constraints": {"pass": order_pass, "total": len(order_results),
                                      "details": order_results},
                "rag_coverage": rag,
                "rule_judge": {"judge_source": "rule_based_offline_replay",
                               "scores": {k: judged[k] for k in ("tool_selection", "rag_relevance", "risk_compliance")}},
                "stage_sequences": stage_calls,
            }
            print(f"  [{SCENARIOS[scenario]['deal_id']}] {scenario} — {SCENARIOS[scenario]['title']}")
            print(f"    期望序列重放命中: {stage_eval['hit_count']}/{stage_eval['expected_count']}"
                  f" = {stage_eval['scenario_tool_accuracy']}；"
                  f"顺序约束 {order_pass}/{len(order_results)}；"
                  f"RAG 覆盖 {len(rag['covered'])}/{len(rag['expected'])}")

    # ---- 汇总指标（仅真实运行场景；离线重放场景单独在 offline_replay 维度报告） ----
    report["metrics"] = {
        "tool_selection_accuracy_avg": round(sum(acc_values) / len(acc_values), 4),
        "per_scenario": {SCENARIOS[s]["deal_id"]: report["scenarios"][s]["tool_selection_accuracy"]
                         for s in run_scenarios},
        "order_constraints_pass": {
            SCENARIOS[s]["deal_id"]: f"{sum(1 for r in report['scenarios'][s]['order_constraints']['details'] if r['pass'])}"
                                     f"/{len(report['scenarios'][s]['order_constraints']['details'])}"
            for s in run_scenarios},
        "rag_coverage_rate": {SCENARIOS[s]["deal_id"]: report["scenarios"][s]["rag_coverage"]["coverage_rate"]
                              for s in run_scenarios},
    }

    AGENT_EVAL_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- eval_report.json 追加 agent_layer_eval（保留原内容） ----
    append_to_eval_report({
        "desc": "Agent 决策层评估维度（由 tools/agent_eval.py 追加；原 Golden/Badcase 工具层指标保持不变）",
        "report_file": AGENT_EVAL_OUT.name,
        "tool_selection_accuracy": report["metrics"]["per_scenario"],
        "tool_selection_accuracy_avg": report["metrics"]["tool_selection_accuracy_avg"],
        "order_constraints_pass": report["metrics"]["order_constraints_pass"],
        "llm_judge_deals": report["llm_judge"]["deals"],
        "offline_replay": {
            sid: info["tool_selection_accuracy"]
            for sid, info in report.get("offline_replay", {}).get("scenarios", {}).items()
        },
    })

    print("=" * 78)
    m = report["metrics"]
    print(f"Agent 层工具选择命中率（3 场景真实运行平均）: {m['tool_selection_accuracy_avg']}")
    print(f"顺序约束: {m['order_constraints_pass']}")
    print(f"RAG 覆盖率: {m['rag_coverage_rate']}")
    if replay_scenarios:
        for sid, info in report["offline_replay"]["scenarios"].items():
            print(f"复合场景离线重放（{info['deal_id']} {sid}）: 期望序列命中 "
                  f"{info['hit_count']}/{info['expected_count']} = {info['tool_selection_accuracy']}；"
                  f"顺序约束 {info['order_constraints']['pass']}/{info['order_constraints']['total']}；"
                  f"RAG 覆盖 {len(info['rag_coverage']['covered'])}/{len(info['rag_coverage']['expected'])}")
    print(f"报告已写入: {AGENT_EVAL_OUT.relative_to(PROJECT)}")
    print(f"judge 证据: llm_judge_DEAL-2002.json / llm_judge_DEAL-2003.json")
    print(f"eval_report.json 已追加 agent_layer_eval 维度（原内容保留）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
