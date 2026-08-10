"""SalesFlow mock 工具网关自检：验证 3 个场景的核心闭环逻辑。

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


def main() -> None:
    global PASS, FAIL
    print(f"Scenarios available: {list_scenarios()}")
    scenario_family_suv()
    scenario_first_car_finance()
    scenario_trade_in_renewal()
    print(f"\n===== RESULT: {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
