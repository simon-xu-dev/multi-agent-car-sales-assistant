"""LLM 自主决策能力独立演示（三个决策点，基于真实 AgentTeams 场景数据）。

本模块独立演示 CarSales 的三个 LLM 自主决策点（基于真实 AgentTeams 场景数据）：
1. 审批门禁（TeamLeader approve/reject/pending）
2. 车型推荐评估（strategy_planner fit_confidence + risk_flag）
3. 工具调用顺序规划（strategy_planner tool_order）

设计原则：
- 只演示 LLM 决策能力本身，不涉及 Worker 调度/编排
- 决策 prompt 只给忠实业务上下文，不操纵决策方向
- decision_source 诚实标注 llm/fallback_config

复现：
    python3 tools/llm_decision_demo.py                    # 无 key → fallback_config
    DASHSCOPE_API_KEY=sk-xxx python3 tools/llm_decision_demo.py  # 真 LLM 推理

证据产物：docs/RUN_EVIDENCE/llm_decision_*.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_client import LLMDecider, _load_dotenv
from mock_tools import LocalMockTools

_load_dotenv()

PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = PROJECT / "docs" / "RUN_EVIDENCE"

# ---- 场景参数（从真实 AgentTeams 运行场景提取的忠实业务数据）----
SCENARIOS: dict[str, dict[str, Any]] = {
    "family_suv_deal": {
        "scenario_id": "family_suv_deal", "deal_id": "DEAL-2001", "deal_type": "new_deal",
        "customer_tier": "normal", "model_code": "L7", "model_name": "理想 L7",
        "guide_price": 329800, "final_price": 318421.6,
        "budget": "25-35 万", "use_case": "家庭自驾游 / 日常通勤",
        "preferences": "六座、空间、安全、新能源",
        "intent_score": 78, "intent_stage": "decision", "priority": "P1",
        "stock_ok": True,
        "approval_type": "discount_override",
        "approval_amount": 50000,
        "approval_reason": "老客置换意向（超授权让步）",
        "authorized_limit": "优惠让步授权底线 1%（约 3298 元）",
        "approval_evidence": "客户为普通新客（CRM 无历史成交记录），让步理由「老客置换意向」与系统记录不符——老客身份不成立，超授权让步缺乏合理依据",
        "fallback_decision": {"decision": "reject", "approver": "门店经理-张伟",
                              "reason": "优惠让步超出授权底线，需重新议价", "outcome": "rollback"},
    },
    "first_car_finance": {
        "scenario_id": "first_car_finance", "deal_id": "DEAL-2002", "deal_type": "finance",
        "customer_tier": "normal", "model_code": "QIN", "model_name": "秦 PLUS",
        "guide_price": 129800, "final_price": 125706.0,
        "budget": "10-15 万", "use_case": "首购代步 / 通勤",
        "preferences": "经济、新能源、智能",
        "intent_score": 65, "intent_stage": "consideration", "priority": "P2",
        "stock_ok": True,
        "approval_type": "credit_authorization",
        "approval_amount": 0,
        "approval_reason": "征信授权审批",
        "authorized_limit": "金融征信需审批，材料齐全方可放行",
        "approval_evidence": "征信材料齐全：身份证 + 6 个月银行流水 + 个人征信报告均已提交并核验通过，客户首购资质符合金融准入",
        "fallback_decision": {"decision": "approve", "approver": "门店经理-李敏",
                              "reason": "征信材料齐全，符合金融准入", "outcome": "confirm"},
    },
    "trade_in_renewal": {
        "scenario_id": "trade_in_renewal", "deal_id": "DEAL-2003", "deal_type": "trade_in",
        "customer_tier": "vip", "model_code": "TANG", "model_name": "唐 DM-i",
        "guide_price": 209800, "final_price": 173000.0,
        "budget": "15-25 万", "use_case": "置换升级 / 家庭出行",
        "preferences": "七座、空间、置换补贴",
        "intent_score": 70, "intent_stage": "decision", "priority": "P1",
        "stock_ok": True,
        "approval_type": "discount_override",
        "approval_amount": 30000,
        "approval_reason": "置换压价（VIP 客户要求额外优惠）",
        "authorized_limit": "优惠让步授权底线 1%（约 2098 元），VIP 额外授权 5%",
        "approval_evidence": "置换佐证不充分：客户为 VIP 但仅口头压价，未提供竞品报价单/旧车残值评估/置换补贴政策依据，重大让步合理性待核",
        "fallback_decision": {"decision": "pending", "approver": "门店经理-待指派",
                              "reason": "议价触及底线，转人工销售，禁止自动放行", "outcome": "human_handoff"},
    },
}


def _build_approval_context(p: dict, tools: LocalMockTools) -> dict[str, Any]:
    """组装审批门禁的忠实业务上下文。"""
    quote_id = "QUOTE-DEMO"
    order_id = "ORD-DEMO"
    order_status = "draft"
    approval_refs = ["APR-DEMO"]
    deal_check = tools.check_deal(p["deal_id"])
    deal_summary = (f"{deal_check.get('summary', '')} 状态={deal_check.get('status', '')} "
                    f"待审{deal_check.get('approvals_pending', 0)}/"
                    f"通过{deal_check.get('approvals_approved', 0)}/"
                    f"驳回{deal_check.get('approvals_rejected', 0)}")
    return {
        "scenario_id": p["scenario_id"], "deal_type": p["deal_type"],
        "customer_tier": p["customer_tier"], "model_code": p["model_code"],
        "price": p["guide_price"], "quote_id": quote_id,
        "approval_type": p["approval_type"],
        "approval_detail": f"优惠金额 {p['approval_amount']} 让步原因「{p['approval_reason']}」",
        "authorization_info": p["authorized_limit"],
        "evidence_status": p["approval_evidence"],
        "memory_recall": "无（首单，无可复用历史经验）",
        "order_id": order_id, "order_status": order_status,
        "approval_refs": approval_refs,
        "deal_summary": deal_summary,
    }


def _build_recommendation_context(p: dict) -> dict[str, Any]:
    """组装车型推荐的忠实业务上下文。"""
    return {
        "scenario_id": p["scenario_id"], "deal_type": p["deal_type"],
        "customer_tier": p["customer_tier"],
        "budget": p["budget"], "use_case": p["use_case"],
        "preferences": p["preferences"],
        "intent_score": p["intent_score"], "intent_stage": p["intent_stage"],
        "priority": p["priority"],
        "model_code": p["model_code"], "model_name": p["model_name"],
        "guide_price": p["guide_price"], "final_price": p["final_price"],
        "stock_ok": p["stock_ok"],
        "memory_recall": "无（首单，无可复用历史经验）",
    }


def _build_tool_context(p: dict) -> dict[str, Any]:
    """组装工具调用顺序规划的忠实业务上下文。"""
    return {
        "scenario_id": p["scenario_id"], "deal_type": p["deal_type"],
        "customer_tier": p["customer_tier"],
        "model_code": p["model_code"], "budget": p["budget"],
        "intent_score": str(p["intent_score"]), "intent_stage": p["intent_stage"],
    }


def run_demo() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    decider = LLMDecider()
    src = (f"百炼 {decider.model}" if decider.available
           else "未配置 API Key → 降级配置驱动")
    print(f"LLM 自主决策能力演示（三个决策点）")
    print(f"决策来源: {src}")
    print("=" * 70)

    all_results: dict[str, dict] = {}

    for sid, p in SCENARIOS.items():
        tools = LocalMockTools(sid)
        result: dict[str, Any] = {"scenario_id": sid, "deal_id": p["deal_id"]}

        # ---- 决策点 1：审批门禁 ----
        ctx1 = _build_approval_context(p, tools)
        out1 = decider.decide(ctx1, fallback=p["fallback_decision"], scenario_id=sid)
        result["approval_gate"] = {
            "context": ctx1, "outcome": out1,
        }
        print(f"\n[{p['deal_id']}] {sid}")
        print(f"  审批门禁: {out1['decision']} [{out1.get('decision_source', '?')}] "
              f"→ {out1.get('outcome', '?')}")
        if out1.get('reason'):
            print(f"    理由: {out1['reason'][:80]}")

        # ---- 决策点 2：车型推荐评估 ----
        ctx2 = _build_recommendation_context(p)
        fallback_rec = {"recommendation_reason": "画像匹配，库存可用",
                        "fit_confidence": "medium", "risk_flag": "none"}
        out2 = decider.recommend(ctx2, fallback=fallback_rec, scenario_id=sid)
        result["recommendation_review"] = {
            "context": ctx2, "outcome": out2,
        }
        print(f"  推荐审查: fit={out2.get('fit_confidence', '?')} "
              f"risk={out2.get('risk_flag', '?')} [{out2.get('decision_source', '?')}]")
        if out2.get('recommendation_reason'):
            print(f"    理由: {out2['recommendation_reason'][:80]}")

        # ---- 决策点 3：工具调用顺序 ----
        ctx3 = _build_tool_context(p)
        fallback_order = ["mock_inventory.list_models", "mock_inventory.check_stock",
                          "mock_price.get_policy", "mock_price.calc_quote"]
        out3 = decider.plan_tool_calls(ctx3, fallback=fallback_order, scenario_id=sid)
        result["tool_planning"] = {
            "context": ctx3, "outcome": out3,
        }
        short = [t.replace("mock_", "").replace("inventory.", "").replace("price.", "")
                 for t in (out3.get("tool_order") or [])]
        print(f"  工具顺序: {'→'.join(short)} [{out3.get('decision_source', '?')}]")
        if out3.get('planning_reason'):
            print(f"    理由: {out3['planning_reason'][:80]}")

        # 证据落盘
        (EVIDENCE_DIR / f"llm_decision_{p['deal_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        all_results[sid] = result

    # 汇总
    summary = {
        "total_scenarios": len(all_results),
        "decision_source": out1.get("decision_source", "unknown"),
        "llm_model": decider.model if decider.available else None,
        "scenarios": {sid: {
            "approval_decision": r["approval_gate"]["outcome"].get("decision"),
            "recommendation_fit": r["recommendation_review"]["outcome"].get("fit_confidence"),
            "recommendation_risk": r["recommendation_review"]["outcome"].get("risk_flag"),
            "tool_order": r["tool_planning"]["outcome"].get("tool_order"),
        } for sid, r in all_results.items()},
    }
    (EVIDENCE_DIR / "llm_decision_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'=' * 70}")
    print(f"证据已写入: {EVIDENCE_DIR.relative_to(PROJECT)}/llm_decision_*.json")
    print(f"汇总: {EVIDENCE_DIR.relative_to(PROJECT)}/llm_decision_summary.json")
    print(f"===== LLM DECISION DEMO: DONE =====")


if __name__ == "__main__":
    run_demo()
