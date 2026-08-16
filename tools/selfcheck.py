"""CarSales mock 工具网关自检：验证 4 个场景的核心闭环逻辑。

用法: python3 tools/selfcheck.py
不需要启动 HTTP 服务器，直接调用 LocalMockTools 验证业务逻辑。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_tools import LocalMockTools, list_scenarios


PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def scenario_family_suv() -> None:
    print("\n== family_suv_deal: 家庭 SUV 全链路成交 ==")
    t = LocalMockTools("family_suv_deal")

    sessions = t.list_sessions()
    check("多渠道会话返回 3 条", len(sessions) == 3, f"got {len(sessions)}")

    lead = t.get_lead()
    check("线索初始状态 new", lead["stage"] == "new")

    t.update_lead_stage(lead["lead_id"], "contacted")
    check("状态机流转 contacted", t.get_lead()["stage"] == "contacted")

    history = t.get_customer_history()
    check("客户历史记忆返回", len(history) >= 1)

    models = t.list_models()
    check("车型目录 3 款", len(models) == 3)

    stock = t.check_stock("L7", "store_001")
    check("L7 库存可用", stock["available"] >= 1)

    policy = t.get_policy()
    check("报价政策授权上限 1%", policy["authorized_max_discount_pct"] == 1.0)

    quote = t.calc_quote("L7", "normal")
    check("报价生成", quote["quote_id"].startswith("QUOTE-"))
    expected = round(329800 - 329800 * 0.008 - 8000, 2)
    check("报价计算正确", quote["final_price"] == expected, f"got {quote['final_price']}")

    slots = t.list_slots("store_001", "L7")
    check("试驾档期存在", len(slots) >= 1)
    booking = t.book_slot("CUST-2001", "store_001", slots[0]["slot"], "L7")
    check("试驾预约 L1 自动成功", booking["status"] == "booked" and booking["risk_level"] == "L1")

    discount = t.apply_discount(quote["quote_id"], 15000, "客户要求额外优惠")
    check("超授权优惠生成 L2 审批", discount["status"] == "needs_approval" and discount["risk_level"] == "L2", str(discount))
    check("审批任务创建", discount["approval_id"].startswith("APR-"))

    discount_ok = t.apply_discount(quote["quote_id"], 1000, "授权内小额优惠")
    check("授权内优惠自动应用", discount_ok["status"] == "applied" and discount_ok["risk_level"] == "L1")

    reserve = t.reserve_car("L7", "store_001")
    check("库存预留 L1", reserve["status"] == "reserved")

    order = t.create_order("LEAD-2001", quote["quote_id"], "LEAD-2001|QUOTE-1")
    check("订单草稿 L2 创建", order["status"] == "draft" and order["risk_level"] == "L2")
    order2 = t.create_order("LEAD-2001", quote["quote_id"], "LEAD-2001|QUOTE-1")
    check("订单幂等（同 order_key 不重复创建）", order2["order_id"] == order["order_id"])

    deal = t.check_deal("DEAL-2001")
    check("闭环验证 pending_approval", deal["status"] == "pending_approval", str(deal["status"]))

    rollback = t.rollback_order(order["order_id"])
    check("订单回滚成功", rollback["status"] == "cancelled")

    case = t.save_case({"title": "测试案例", "summary": "家庭 SUV 成交", "key_actions": ["试驾前置"]})
    check("案例入库", case["status"] == "saved" and case["case_id"].startswith("CASE-"))

    cases = t.search_case("家庭 SUV")
    check("案例 RAG 检索命中", len(cases) >= 1)
    check("工具调用 Trace 留痕", len(t.trace) >= 10, f"trace={len(t.trace)}")

    # ---- 真实运行失败查询回归（加权 OR 检索后应命中，不再空结果） ----
    prod_rag = t.search_product("新能源六座SUV 25万")
    check("RAG 长句产品检索命中（真实失败查询回归）", len(prod_rag) >= 1, f"got {len(prod_rag)}")
    sop_rag = t.search_sop("家庭SUV 新能源 六座 试驾 意图评估 BANT")
    check("RAG SOP 长句检索命中（含 BANT 信号词）", len(sop_rag) >= 1, f"got {len(sop_rag)}")
    sig_rag = t.search_sop("成交信号")
    check("RAG 成交信号检索命中", len(sig_rag) >= 1, f"got {len(sig_rag)}")
    follow_rag = t.search_sop("跟进")
    check("RAG 跟进 SOP 检索命中", len(follow_rag) >= 1, f"got {len(follow_rag)}")
    case_rag = t.search_case("家庭购车 二胎 SUV 试驾体验")
    check("RAG 案例长句检索命中", len(case_rag) >= 1, f"got {len(case_rag)}")

    # ---- 门店别名映射（真实运行时 LLM 从任务文本推断门店名） ----
    stock_alias = t.check_stock("L7", "HZ-BINJIANG")
    check("门店别名 HZ-BINJIANG 库存可查", stock_alias["available"] >= 1, str(stock_alias))
    slots_alias = t.list_slots("杭州滨江旗舰店", "L7")
    check("门店中文名试驾档期可查", len(slots_alias) >= 1, f"got {len(slots_alias)}")


def scenario_first_car_finance() -> None:
    print("\n== first_car_finance: 首购金融方案 ==")
    t = LocalMockTools("first_car_finance")

    models = t.list_models()
    check("车型目录 3 款", len(models) == 3)

    quote = t.calc_quote("QIN", "normal")
    plan = t.calc_plan(quote["final_price"], 30000, 36)
    check("金融方案生成 2 组", len(plan["plans"]) == 2)
    check("月供可复算", plan["plans"][0]["monthly_payment"] > 0)

    approval = t.submit_approval(plan["plans"][0]["plan_id"], "CUST-2002")
    check("征信授权 L2 审批任务", approval["status"] == "created" and approval["risk_level"] == "L2")

    status = t.check_approval(approval["approval_id"])
    check("审批状态查询", status["status"] == "pending")

    order = t.create_order("LEAD-2002", quote["quote_id"], "LEAD-2002|QUOTE-1")
    check("审批前订单仅草稿", order["status"] == "draft")

    deal = t.check_deal("DEAL-2002")
    check("闭环验证 pending_approval", deal["status"] == "pending_approval")


def scenario_trade_in_renewal() -> None:
    print("\n== trade_in_renewal: 老客户置换与售后 ==")
    t = LocalMockTools("trade_in_renewal")

    history = t.get_customer_history("CUST-2003")
    check("历史记忆召回（3 年老客户）", len(history) >= 3, f"got {len(history)}")

    cases = t.search_case("老客户 置换")
    check("置换案例 RAG 命中", len(cases) >= 1)

    sop = t.search_sop("置换")
    check("置换 SOP 命中", len(sop) >= 1)

    quote = t.calc_quote("TANG", "silver")
    discount = t.apply_discount(quote["quote_id"], 30000, "客户要求 3 万额外优惠")
    check("3 万额外优惠超授权 -> L2", discount["status"] == "needs_approval" and discount["risk_level"] == "L2")

    # 议价底线：总让步超过授权且接近底线 -> 停止自动让步（由 negotiation-guard 语义保证，
    # 工具层表现为 apply_discount 持续返回 needs_approval 而非放行）
    again = t.apply_discount(quote["quote_id"], 30000, "再次申请同样优惠")
    check("底线守护：重复大额让步不放行", again["status"] == "needs_approval")

    touch = t.send_template_message("CUST-2003", "renewal_reminder", {"benefit": "续保9折"})
    check("售后模板消息 L1 发送", touch["status"] == "sent" and touch["risk_level"] == "L1")

    deal = t.check_deal("DEAL-2003")
    check("闭环验证 pending_approval", deal["status"] == "pending_approval")


def scenario_trade_in_finance() -> None:
    """DEAL-2004 置换+金融复合场景：双 L2 审批门禁叠加 + 议价底线守护 + 订单幂等。"""
    print("\n== trade_in_finance: 置换+金融双审批复合场景 ==")
    t = LocalMockTools("trade_in_finance")

    # ---- 线索归并与老客户画像 ----
    sessions = t.list_sessions()
    check("多渠道会话归并 3 条", len(sessions) == 3, f"got {len(sessions)}")
    lead = t.get_lead()
    check("老客户线索 gold 等级", lead.get("loyalty_tier") == "gold" and lead.get("is_repeat_customer") is True)
    history = t.get_customer_history("CUST-2004")
    check("3 年老客户历史记忆召回", len(history) >= 3, f"got {len(history)}")

    # ---- 置换评估（L0）与新车报价（gold）----
    assessment = t.assess_vehicle("比亚迪汉 DM-i 冠军版", 56000)
    check("旧车置换评估 L0 计算", assessment["standard_offer"] == 132000 and assessment["risk_level"] == "L0")
    check("置换总价值 = 评估价 + 补贴", assessment["total_trade_in_value"] == 147000)

    quote = t.calc_quote("L9", "gold")
    expected = round(459800 - 459800 * 0.013 - 10000, 2)
    check("L9 gold 报价计算正确", quote["final_price"] == expected, f"got {quote['final_price']}")

    # ---- 金融缺口方案：置换总价值 + 自有资金 12 万冲抵 ----
    down_total = assessment["total_trade_in_value"] + 120000
    plan = t.calc_plan(quote["final_price"], down_total, 36)
    check("金融方案生成 2 组", len(plan["plans"]) == 2)
    loan = quote["final_price"] - down_total
    r = 0.0299 / 12
    expected_monthly = round(loan * r / (1 - (1 + r) ** -36), 2)
    check("厂家低息月供可复算", plan["plans"][0]["monthly_payment"] == expected_monthly,
          f"got {plan['plans'][0]['monthly_payment']} expect {expected_monthly}")

    # ---- 双 L2 审批门禁：征信授权 + 置换估值上浮 ----
    credit = t.submit_approval(plan["plans"][0]["plan_id"], "CUST-2004")
    check("征信授权 L2 审批任务", credit["status"] == "created" and credit["risk_level"] == "L2")

    uplift = t.request_uplift(assessment["assessment_id"], 150000, "客户要求旧车按 15 万收")
    check("估值上浮 1.8 万超授权 -> L2", uplift["status"] == "needs_approval" and uplift["risk_level"] == "L2")
    check("置换估值审批任务创建", uplift["approval_id"].startswith("APR-"))

    # 授权内估值上浮（另一评估单）：L1 自动应用
    a2 = t.assess_vehicle("比亚迪汉 DM-i 冠军版", 56000)
    up2 = t.request_uplift(a2["assessment_id"], 138000, "授权内小幅上浮")
    check("授权内估值上浮 L1 自动应用", up2["status"] == "applied" and up2["risk_level"] == "L1")

    # 幂等：同评估单同估值重复申请返回原审批，不重复创建
    up3 = t.request_uplift(assessment["assessment_id"], 150000, "重复申请 15 万估值")
    check("估值上浮申请幂等去重", up3.get("deduplicated") is True and up3["approval_id"] == uplift["approval_id"])

    # ---- 议价与置换上浮叠加的底线守护 ----
    stack1 = t.apply_discount(quote["quote_id"], 35000, "置换+金融客户要求叠加 3.5 万优惠")
    check("叠加 3.5 万超授权优惠 -> L2 审批", stack1["status"] == "needs_approval")
    stack2 = t.apply_discount(quote["quote_id"], 35000, "再次申请叠加优惠（触底）")
    check("底线守护：叠加让步重复申请不放行", stack2["status"] == "needs_approval")

    deal = t.check_deal("DEAL-2004")
    # 待审 4 项 = 征信授权 + 置换估值上浮 + 两笔叠加让步申请（apply_discount 重复申请各自建审批，均待人工决策）
    check("闭环验证 pending_approval（双审批+叠加让步申请待审）",
          deal["status"] == "pending_approval" and deal["approvals_pending"] == 4,
          str(deal.get("approvals_pending")))

    # ---- 转人工闭环：人工统一驳回两笔叠加现金优惠（守底线，改权益补偿）----
    rj = t.reject(stack1["approval_id"], "门店经理-王芳", "估值上浮已让 1.8 万，叠加 3.5 万现金优惠触总让步底线，改赠延保权益")
    check("叠加优惠驳回（转人工后守底线）", rj["status"] == "rejected")
    rj2 = t.reject(stack2["approval_id"], "门店经理-王芳", "重复让步申请同样驳回，维持底线")
    check("重复让步申请同样驳回", rj2["status"] == "rejected")

    # ---- 订单：双审批关联 + 幂等 ----
    order = t.create_order("LEAD-2004", quote["quote_id"], "LEAD-2004|QUOTE-1")
    check("订单草稿 L2 创建", order["status"] == "draft" and order["risk_level"] == "L2")
    refs = order.get("approval_refs", [])
    check("订单快照关联双审批（征信+估值，不含已驳回）",
          uplift["approval_id"] in refs and credit["approval_id"] in refs
          and stack1["approval_id"] not in refs and stack2["approval_id"] not in refs,
          str(refs))
    order2 = t.create_order("LEAD-2004", quote["quote_id"], "LEAD-2004|QUOTE-1")
    check("订单幂等（同 order_key 不重复创建）", order2["order_id"] == order["order_id"])

    # ---- 双审批依赖：未批/半批均拦截，齐备后放行 ----
    blocked0 = t.confirm_order(order["order_id"])
    check("双审批均未批 confirm 被拦截", blocked0["status"] == "blocked" and blocked0["blocked_reason"] == "pending_approvals")

    ap_uplift = t.approve(uplift["approval_id"], "门店经理-王芳", "估值上浮 1.8 万在可接受区间")
    check("置换估值审批通过", ap_uplift["status"] == "approved")
    blocked1 = t.confirm_order(order["order_id"])
    check("征信未批 confirm 仍被拦截（双审批依赖）", blocked1["status"] == "blocked"
          and blocked1["blocked_reason"] == "pending_approvals"
          and credit["approval_id"] in blocked1["pending_approvals"], str(blocked1))

    ap_credit = t.approve(credit["approval_id"], "门店经理-王芳", "征信授权合规，客户已线上确认")
    check("征信审批通过", ap_credit["status"] == "approved")
    confirmed = t.confirm_order(order["order_id"])
    check("双审批齐备后订单确认", confirmed["status"] == "confirmed")

    # ---- RAG 证据与审计 ----
    sop = t.search_sop("置换 金融 复合 双审批 征信 估值")
    check("复合场景 SOP RAG 命中", len(sop) >= 1)
    case = t.search_case("置换 金融 复合 双审批 成交")
    check("复合场景案例 RAG 命中", len(case) >= 1)

    at = t.audit_trail()
    names = [a["name"] for a in at]
    check("审计轨迹含估值审批+驳回+确认",
          "trade_in_valuation_override" in names and "reject_approval" in names and "confirm_order" in names)

    touch = t.send_template_message("CUST-2004", "trade_in_delivery_reminder", {"benefit": "置换补贴15000"})
    check("交付关怀模板消息 L1 发送", touch["status"] == "sent" and touch["risk_level"] == "L1")
    check("工具调用 Trace 留痕", len(t.trace) >= 15, f"trace={len(t.trace)}")


def scenario_approval_audit_loop() -> None:
    """P2.3 安全审计闭环：approve/reject -> confirm/rollback -> audit_trail 端到端。"""
    print("\n== approval_audit_loop: 审批决策 -> 回滚/确认 -> 审计轨迹 ==")

    # ---- 路径 A：reject -> confirm 被门禁拦截 -> rollback -> 审计 ----
    t = LocalMockTools("family_suv_deal")
    q = t.calc_quote("L7", "gold")
    d = t.apply_discount(q["quote_id"], 999999, "超授权让步")
    check("超授权优惠生成 L2 审批", d["status"] == "needs_approval" and d["risk_level"] == "L2")
    aid = d["approval_id"]
    o = t.create_order("LEAD-1001", q["quote_id"], "KEY-AUDIT-SC")
    check("订单快照关联 approval_refs", aid in o.get("approval_refs", []))
    # 驳回（决策层只标记，不自动回滚）
    rj = t.reject(aid, "门店经理-张伟", "让步超出底线")
    check("审批驳回 pending->rejected", rj["status"] == "rejected")
    check("驳回标记关联订单 rollback_requested", o["order_id"] in rj["affected_orders"])
    # 门禁：驳回后 confirm 必须被拦截（高风险动作禁止默认放行）
    cb = t.confirm_order(o["order_id"])
    check("驳回后 confirm 被门禁拦截", cb["status"] == "blocked" and cb["blocked_reason"] == "rejected_approvals")
    # 显式回滚（决策与执行分离）
    rb = t.rollback_order(o["order_id"])
    check("订单回滚 cancelled + 回滚点 draft", rb["status"] == "cancelled" and rb["rollback_point"] == "draft")
    # 幂等：重复 reject 返回当前状态，不二次变更
    rj2 = t.reject(aid, "另一经理", "重复")
    check("重复驳回幂等", rj2["status"] == "rejected" and "不可重复决策" in rj2["message"])
    # 审计轨迹
    at = t.audit_trail()
    names = [a["name"] for a in at]
    check("审计轨迹含驳回+回滚", "reject_approval" in names and "rollback_order" in names)
    af = t.audit_trail(approval_id=aid)
    check("审计轨迹按 approval_id 筛选", all(a.get("approval_id") == aid for a in af) and len(af) >= 1)
    cd = t.check_deal("DEAL-AUDIT-SC")
    check("闭环验证 rolled_back", cd["status"] == "rolled_back" and cd["approvals_rejected"] == 1)

    # ---- 路径 B：approve -> confirm -> won ----
    t2 = LocalMockTools("family_suv_deal")
    q2 = t2.calc_quote("L7", "gold")
    d2 = t2.apply_discount(q2["quote_id"], 999999, "超授权")
    aid2 = d2["approval_id"]
    o2 = t2.create_order("LEAD-1001", q2["quote_id"], "KEY-AUDIT-SC2")
    ap = t2.approve(aid2, "门店经理-李敏", "符合底线")
    check("审批通过 pending->approved", ap["status"] == "approved")
    cf = t2.confirm_order(o2["order_id"])
    check("通过后订单确认 confirmed", cf["status"] == "confirmed")
    cd2 = t2.check_deal("DEAL-AUDIT-SC2")
    check("闭环验证 won", cd2["status"] == "won" and cd2["approvals_approved"] == 1)


def main() -> None:
    global PASS, FAIL
    print(f"Scenarios available: {list_scenarios()}")
    scenario_family_suv()
    scenario_first_car_finance()
    scenario_trade_in_renewal()
    scenario_trade_in_finance()
    scenario_approval_audit_loop()
    print(f"\n===== RESULT: {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
