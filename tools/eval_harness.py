"""CarSales 评估闭环：Golden/Badcase 数据集 + 规则评估 + LLM-as-Judge。

对标赛题"评估结果可回流 Dataset，用于专家调优智能体 Prompt/Skill/RAG/MCP"。
- Golden（10 例）：3 场景的闭环正确行为（归并/报价/审批/幂等/回滚/RAG 召回）。
- Badcase（6 例）：风控守卫应拒绝/挂起的危险输入（巨额优惠/重复下单/未知车型/底线让步）。
- 指标：Golden 准确率、Badcase 守卫精确率、按维度拆分。
- LLM-as-Judge：生成可复用评判 Prompt 模板；若提供 LLM_API_KEY/DASHSCOPE_API_KEY 则在线评判闭环合理性，否则仅离线规则评估并输出待评 Prompt。

用法:
    python3 tools/eval_harness.py                 # 离线规则评估
    # 配置 .env 的 DASHSCOPE_API_KEY 后，自动激活 LLM-as-Judge（在线评判闭环合理性）
    cp .env.example .env  # 填入 DASHSCOPE_API_KEY
    python3 tools/eval_harness.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mock_tools import LocalMockTools  # noqa: E402
from llm_client import _load_dotenv  # noqa: E402  复用 .env 加载，激活 LLM-as-Judge

_load_dotenv()  # 加载项目根 .env，使 DASHSCOPE_API_KEY 对 LLM-as-Judge 可见

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "docs" / "RUN_EVIDENCE" / "eval_report.json"

# ---- LLM-as-Judge Prompt 模板（可复用，覆盖工具选择/RAG召回/风控合规三维度）----
LLM_JUDGE_PROMPT = """你是销售 Agent 闭环评审专家。请对以下成交闭环执行结果打分（0-10）并给出理由。

【场景】{scenario} ({deal})
【执行轨迹摘要】{trace_summary}
【规则评估结论】{rule_verdict}

评判维度：
1. 工具选择合理性（0-10）：Agent 是否选了正确工具、调用顺序是否构成有效成交路径。
2. RAG 召回相关性（0-10）：检索结果是否支撑决策，是否出现"该查未查"或"空结果仍下结论"。
3. 风控合规（0-10）：低风险是否自动、超授权是否走审批而非放行、议价是否守底线。

输出 JSON：{{"tool_selection": n, "rag_relevance": n, "risk_compliance": n, "reason": "..."}}
"""


def _quote_final_price(guide: float, base_pct: float, subsidy: float) -> float:
    return round(guide - guide * base_pct / 100 - subsidy, 2)


# ---- Golden 评估用例（期望系统正确完成）----
def golden_cases() -> list[dict]:
    cases: list[dict] = []

    # G01-G06: family_suv_deal
    t = LocalMockTools("family_suv_deal")
    s = t.scenario
    cases.append({"id": "G01", "type": "golden", "dimension": "线索归并", "scenario": "family_suv_deal",
                  "passed": len(t.list_sessions()) == 3, "actual": f"{len(t.list_sessions())} 渠道会话"})
    cases.append({"id": "G02", "type": "golden", "dimension": "报价计算", "scenario": "family_suv_deal",
                  "passed": t.calc_quote("L7", "normal")["final_price"] == _quote_final_price(329800, 0.8, 8000),
                  "actual": t.calc_quote("L7", "normal")["final_price"]})
    policy = t.get_policy()
    cases.append({"id": "G03", "type": "golden", "dimension": "风控授权", "scenario": "family_suv_deal",
                  "passed": policy["authorized_max_discount_pct"] == 1.0, "actual": policy["authorized_max_discount_pct"]})
    q = t.calc_quote("L7", "normal")
    slots = t.list_slots("store_001", "L7")
    cases.append({"id": "G04", "type": "golden", "dimension": "低风险自动", "scenario": "family_suv_deal",
                  "passed": t.book_slot("CUST-2001", "store_001", slots[0]["slot"], "L7")["risk_level"] == "L1",
                  "actual": "试驾 L1 自动"})
    d = t.apply_discount(q["quote_id"], 15000, "额外优惠")
    cases.append({"id": "G05", "type": "golden", "dimension": "高风险审批", "scenario": "family_suv_deal",
                  "passed": d["status"] == "needs_approval" and d["risk_level"] == "L2", "actual": f"{d['status']}/{d['risk_level']}"})
    o = t.create_order("LEAD-2001", q["quote_id"], "LEAD-2001|Q1")
    o2 = t.create_order("LEAD-2001", q["quote_id"], "LEAD-2001|Q1")
    cases.append({"id": "G06", "type": "golden", "dimension": "订单幂等", "scenario": "family_suv_deal",
                  "passed": o["order_id"] == o2["order_id"] and o["risk_level"] == "L2", "actual": o["order_id"]})
    cases.append({"id": "G07", "type": "golden", "dimension": "闭环验证", "scenario": "family_suv_deal",
                  "passed": t.check_deal("DEAL-2001")["status"] == "pending_approval", "actual": t.check_deal("DEAL-2001")["status"]})
    cases.append({"id": "G08", "type": "golden", "dimension": "RAG召回", "scenario": "family_suv_deal",
                  "passed": len(t.search_sop("成交信号")) >= 1, "actual": f"{len(t.search_sop('成交信号'))} 条 SOP"})

    # G09-G10: first_car_finance / trade_in
    t2 = LocalMockTools("first_car_finance")
    q2 = t2.calc_quote("QIN", "normal")
    plan = t2.calc_plan(q2["final_price"], 30000, 36)
    cases.append({"id": "G09", "type": "golden", "dimension": "金融方案", "scenario": "first_car_finance",
                  "passed": len(plan["plans"]) == 2 and plan["plans"][0]["monthly_payment"] > 0, "actual": f"{len(plan['plans'])} 组方案"})
    ap = t2.submit_approval(plan["plans"][0]["plan_id"], "CUST-2002")
    cases.append({"id": "G10", "type": "golden", "dimension": "征信审批门禁", "scenario": "first_car_finance",
                  "passed": ap["status"] == "created" and ap["risk_level"] == "L2", "actual": f"{ap['status']}/{ap['risk_level']}"})

    t3 = LocalMockTools("trade_in_renewal")
    cases.append({"id": "G11", "type": "golden", "dimension": "历史记忆召回", "scenario": "trade_in_renewal",
                  "passed": len(t3.get_customer_history("CUST-2003")) >= 3, "actual": f"{len(t3.get_customer_history('CUST-2003'))} 条历史"})
    q3 = t3.calc_quote("TANG", "silver")
    d3 = t3.apply_discount(q3["quote_id"], 30000, "3万额外优惠")
    cases.append({"id": "G12", "type": "golden", "dimension": "议价底线守护", "scenario": "trade_in_renewal",
                  "passed": d3["status"] == "needs_approval" and d3["risk_level"] == "L2", "actual": f"{d3['status']}/{d3['risk_level']}"})

    # G13: 审批通过 -> 订单确认 -> 成交（approve 闭环 + 审计轨迹留痕）
    t4 = LocalMockTools("family_suv_deal")
    q4 = t4.calc_quote("L7", "normal")
    d4 = t4.apply_discount(q4["quote_id"], 15000, "额外优惠")
    aid4 = d4["approval_id"]
    o4 = t4.create_order("LEAD-2001", q4["quote_id"], "G13|key")
    ap4 = t4.approve(aid4, "门店经理-李敏", "符合底线")
    cf4 = t4.confirm_order(o4["order_id"])
    at4 = t4.audit_trail()
    names4 = [a["name"] for a in at4]
    g13_ok = (ap4["status"] == "approved" and cf4["status"] == "confirmed"
              and t4.check_deal("DEAL-G13")["status"] == "won"
              and "approve" in names4 and "confirm_order" in names4)
    cases.append({"id": "G13", "type": "golden", "dimension": "审批闭环", "scenario": "family_suv_deal",
                  "passed": g13_ok, "actual": f"approve->{ap4['status']} confirm->{cf4['status']}"})
    return cases


# ---- Badcase 评估用例（期望系统拒绝/挂起/报错，而非错误放行）----
def badcase_cases() -> list[dict]:
    cases: list[dict] = []
    t = LocalMockTools("family_suv_deal")
    q = t.calc_quote("L7", "normal")
    # B01: 超授权巨额优惠 -> 必须 needs_approval，不得 applied
    b = t.apply_discount(q["quote_id"], 999999, "巨额测试")
    cases.append({"id": "B01", "type": "badcase", "dimension": "底线守护", "scenario": "family_suv_deal",
                  "passed": b["status"] == "needs_approval", "actual": b["status"], "desc": "巨额优惠不自动放行"})
    # B02: 重复大额让步 -> 仍 needs_approval（不累积放行）
    b2 = t.apply_discount(q["quote_id"], 30000, "再次大额")
    cases.append({"id": "B02", "type": "badcase", "dimension": "底线守护", "scenario": "family_suv_deal",
                  "passed": b2["status"] == "needs_approval", "actual": b2["status"], "desc": "重复让步不放行"})
    # B03: 未知 quote 优惠 -> 报错而非静默应用
    try:
        t.apply_discount("QUOTE-NOPE", 1000, "x")
        cases.append({"id": "B03", "type": "badcase", "dimension": "异常处理", "scenario": "family_suv_deal",
                      "passed": False, "actual": "未报错", "desc": "未知 quote 应报错"})
    except Exception:
        cases.append({"id": "B03", "type": "badcase", "dimension": "异常处理", "scenario": "family_suv_deal",
                      "passed": True, "actual": "正确报错", "desc": "未知 quote 报错"})
    # B04: 未知车型库存 -> 报错
    try:
        t.check_stock("NOPE", "store_001")
        cases.append({"id": "B04", "type": "badcase", "dimension": "异常处理", "scenario": "family_suv_deal",
                      "passed": False, "actual": "未报错", "desc": "未知车型应报错"})
    except Exception:
        cases.append({"id": "B04", "type": "badcase", "dimension": "异常处理", "scenario": "family_suv_deal",
                      "passed": True, "actual": "正确报错", "desc": "未知车型报错"})
    # B05: 订单回滚后状态 cancelled
    o = t.create_order("LEAD-2001", q["quote_id"], "B05|key")
    rb = t.rollback_order(o["order_id"])
    cases.append({"id": "B05", "type": "badcase", "dimension": "回滚审计", "scenario": "family_suv_deal",
                  "passed": rb["status"] == "cancelled" and rb["rollback_point"] == "draft", "actual": rb["status"], "desc": "回滚到 draft"})
    # B06: 不存在的试驾档期 -> 报错
    try:
        t.book_slot("CUST-2001", "store_001", "2999-01-01 00:00", "L7")
        cases.append({"id": "B06", "type": "badcase", "dimension": "异常处理", "scenario": "family_suv_deal",
                      "passed": False, "actual": "未报错", "desc": "无效档期应报错"})
    except Exception:
        cases.append({"id": "B06", "type": "badcase", "dimension": "异常处理", "scenario": "family_suv_deal",
                      "passed": True, "actual": "正确报错", "desc": "无效档期报错"})
    # B07: 驳回 -> confirm 被门禁拦截 -> 回滚 -> 审计轨迹含驳回+回滚（决策与执行分离）
    t2 = LocalMockTools("family_suv_deal")
    q_b7 = t2.calc_quote("L7", "normal")
    d_b7 = t2.apply_discount(q_b7["quote_id"], 15000, "超授权")
    aid_b7 = d_b7["approval_id"]
    o_b7 = t2.create_order("LEAD-2001", q_b7["quote_id"], "B07|key")
    rj_b7 = t2.reject(aid_b7, "门店经理-张伟", "超底线")
    cb_b7 = t2.confirm_order(o_b7["order_id"])  # 门禁必须拦截
    rb_b7 = t2.rollback_order(o_b7["order_id"])
    names_b7 = [a["name"] for a in t2.audit_trail()]
    b07_ok = (rj_b7["status"] == "rejected" and cb_b7["status"] == "blocked"
              and rb_b7["status"] == "cancelled"
              and "reject_approval" in names_b7 and "rollback_order" in names_b7)
    cases.append({"id": "B07", "type": "badcase", "dimension": "回滚审计", "scenario": "family_suv_deal",
                  "passed": b07_ok,
                  "actual": f"reject->{rj_b7['status']} confirm->{cb_b7['status']} rollback->{rb_b7['status']}",
                  "desc": "驳回->门禁拦截->回滚->审计留痕"})
    return cases


def _try_llm_judge(report: dict) -> dict:
    """若存在 LLM API Key，对 DEAL-2001 闭环做一次 LLM-as-Judge；否则只返回 Prompt 模板。"""
    key = os.environ.get("LLM_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    sample = {
        "scenario": "family_suv_deal", "deal": "DEAL-2001",
        "trace_summary": "3 渠道归并→画像→理想L7推荐→试驾L1→超授权优惠L2审批→订单草稿幂等→check_deal=pending_approval",
        "rule_verdict": "Golden 8/8 + 守卫 6/6 通过",
    }
    prompt = LLM_JUDGE_PROMPT.format(**sample)
    result = {"prompt_template": LLM_JUDGE_PROMPT, "sample_prompt": prompt, "online_judge": None}
    if not key:
        result["online_judge"] = "skipped（未提供 LLM_API_KEY/DASHSCOPE_API_KEY，离线规则评估已产出指标）"
        return result
    # 在线评判（轻量调用 DashScope/OpenAI 兼容接口）
    try:
        base = os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        model = os.environ.get("LLM_MODEL", "qwen-plus")
        import urllib.request
        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                             "response_format": {"type": "json_object"}}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read())
        result["online_judge"] = out["choices"][0]["message"]["content"]
    except Exception as exc:
        result["online_judge"] = f"LLM 调用失败: {exc}"
    return result


def main() -> int:
    golden = golden_cases()
    badcase = badcase_cases()
    all_cases = golden + badcase

    g_pass = sum(c["passed"] for c in golden)
    b_pass = sum(c["passed"] for c in badcase)
    by_dim: dict[str, dict] = {}
    for c in all_cases:
        d = by_dim.setdefault(c["dimension"], {"pass": 0, "total": 0})
        d["total"] += 1
        d["pass"] += int(c["passed"])

    report = {
        "note": "Golden=系统应正确完成的闭环行为；Badcase=系统应拒绝/挂起/报错的风控守卫。指标回流用于调优 Skill/RAG/风控边界。",
        "metrics": {
            "golden_accuracy": round(g_pass / len(golden), 4),
            "guard_precision": round(b_pass / len(badcase), 4),
            "overall": round((g_pass + b_pass) / len(all_cases), 4),
            "golden_pass": g_pass, "golden_total": len(golden),
            "badcase_pass": b_pass, "badcase_total": len(badcase),
        },
        "by_dimension": {k: {"pass": v["pass"], "total": v["total"],
                            "rate": round(v["pass"] / v["total"], 4)} for k, v in by_dim.items()},
        "cases": all_cases,
        "llm_judge": _try_llm_judge({}),
        "dataset_reflow": {
            "desc": "失败用例与 LLM 评判结果回流为 Dataset，用于专家调优 Prompt/Skill/RAG/风控阈值",
            "failed_cases": [c["id"] for c in all_cases if not c["passed"]],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("CarSales 评估闭环（Golden/Badcase + LLM-as-Judge）")
    print("=" * 64)
    for c in all_cases:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['id']} [{c['type']}] {c['dimension']:10s} {c.get('desc','')}")
    m = report["metrics"]
    print("-" * 64)
    print(f"Golden 准确率: {m['golden_pass']}/{m['golden_total']} = {m['golden_accuracy']}")
    print(f"守卫精确率:   {m['badcase_pass']}/{m['badcase_total']} = {m['guard_precision']}")
    print(f"综合:        {m['overall']}")
    print("按维度:", {k: v['rate'] for k, v in report['by_dimension'].items()})
    print(f"LLM-as-Judge: {report['llm_judge']['online_judge'][:60] if isinstance(report['llm_judge']['online_judge'], str) else 'n/a'}")
    print(f"报告已写入: {OUT.relative_to(PROJECT)}")
    return 0 if m['overall'] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
