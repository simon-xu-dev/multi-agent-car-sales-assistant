from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = PROJECT_ROOT / "scenarios"

# 线索状态机：新线索 -> 已联系 -> 已识别需求 -> 试驾中 -> 议价中 -> 成交/流失/待审批
LEAD_STAGES = [
    "new",
    "contacted",
    "qualified",
    "test_driving",
    "negotiating",
    "pending_approval",
    "won",
    "lost",
]

# 订单状态机
ORDER_STAGES = ["draft", "pending_approval", "confirmed", "delivered", "cancelled"]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_scenarios() -> List[str]:
    return sorted(path.stem for path in SCENARIO_DIR.glob("*.json"))


def load_scenario(scenario_id: str) -> Dict[str, Any]:
    path = SCENARIO_DIR / f"{scenario_id}.json"
    if not path.exists():
        available = ", ".join(list_scenarios())
        raise ValueError(f"Unknown scenario '{scenario_id}'. Available: {available}")
    return load_json(path)


def compact(value: Any, max_len: int = 180) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


class BaseMockTools:
    """所有 mock 工具服务的抽象基类，保证每个工具都有 trace 记录（可观测）。"""

    def __init__(self, scenario_id: str) -> None:
        self.scenario_id = scenario_id
        self.actions: List[Dict[str, Any]] = []
        self.trace: List[Dict[str, Any]] = []

    def _record(self, tool: str, args: Dict[str, Any], result: Any) -> Any:
        self.trace.append(
            {
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "tool": tool,
                "args": args,
                "result_preview": compact(result),
            }
        )
        return result

    def _action(self, name: str, risk_level: str, details: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
            "name": name,
            "risk_level": risk_level,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            **details,
        }
        self.actions.append(record)
        return record

    def reset(self) -> None:
        self.actions.clear()
        self.trace.clear()

    # ---- mock_crm ----
    def get_lead(self, lead_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def list_sessions(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def get_customer_history(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def update_lead_stage(self, lead_id: str, stage: str) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_inventory ----
    def list_models(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def check_stock(self, model_code: str, store_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def reserve_car(self, model_code: str, store_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_price ----
    def get_policy(self) -> Dict[str, Any]:
        raise NotImplementedError

    def calc_quote(self, model_code: str, customer_tier: str) -> Dict[str, Any]:
        raise NotImplementedError

    def apply_discount(self, quote_id: str, amount: float, reason: str) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_finance ----
    def calc_plan(self, price: float, down_payment: float, months: int) -> Dict[str, Any]:
        raise NotImplementedError

    def submit_approval(self, plan_id: str, customer_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def check_approval(self, approval_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_testdrive ----
    def list_slots(self, store_id: str, model_code: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def book_slot(self, customer_id: str, store_id: str, slot: str, model_code: str) -> Dict[str, Any]:
        raise NotImplementedError

    def cancel_booking(self, booking_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_order ----
    def create_order(self, lead_id: str, quote_id: str, order_key: str) -> Dict[str, Any]:
        raise NotImplementedError

    def get_order(self, order_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def rollback_order(self, order_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_knowledge (RAG) ----
    def search_product(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def search_sop(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def search_case(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def save_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_wechat ----
    def get_session(self, customer_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def send_template_message(self, customer_id: str, template: str, params: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_verify ----
    def check_deal(self, deal_id: str) -> Dict[str, Any]:
        raise NotImplementedError


class LocalMockTools(BaseMockTools):
    """按 scenario 数据驱动执行的 mock 工具实现。"""

    def __init__(self, scenario_id: str) -> None:
        super().__init__(scenario_id)
        self.scenario = load_scenario(scenario_id)
        self.lead_stage = self.scenario["lead"].get("stage", "new")
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.approvals: Dict[str, Dict[str, Any]] = {}
        self.bookings: Dict[str, Dict[str, Any]] = {}
        self.saved_cases: List[Dict[str, Any]] = []
        self.quotes: Dict[str, Dict[str, Any]] = {}
        self._quote_seq = 0

    def _scenario(self, key: str, default: Any) -> Any:
        return self.scenario.get(key, default)

    def _make_quote_id(self) -> str:
        self._quote_seq += 1
        return f"QUOTE-{self.scenario_id.upper()}-{self._quote_seq}"

    def _policy(self) -> Dict[str, Any]:
        return self._scenario("price_policy", {})

    def _model(self, model_code: str) -> Optional[Dict[str, Any]]:
        for model in self._scenario("models", []):
            if model.get("code") == model_code:
                return model
        return None

    # ---- mock_crm ----
    def get_lead(self, lead_id: Optional[str] = None) -> Dict[str, Any]:
        lead = dict(self.scenario["lead"])
        lead["stage"] = self.lead_stage
        return self._record("mock_crm.get_lead", {"lead_id": lead_id}, lead)

    def list_sessions(self) -> List[Dict[str, Any]]:
        return self._record("mock_crm.list_sessions", {}, self._scenario("sessions", []))

    def get_customer_history(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._record(
            "mock_crm.get_customer_history", {"customer_id": customer_id},
            self._scenario("customer_history", []),
        )

    def update_lead_stage(self, lead_id: str, stage: str) -> Dict[str, Any]:
        if stage not in LEAD_STAGES:
            raise ValueError(f"invalid stage '{stage}', allowed: {LEAD_STAGES}")
        self.lead_stage = stage
        result = {"lead_id": lead_id, "stage": stage, "message": f"Lead stage updated to {stage}."}
        self._action("update_lead_stage", "L0", {"lead_id": lead_id, "stage": stage})
        return self._record("mock_crm.update_lead_stage", {"lead_id": lead_id, "stage": stage}, result)

    # ---- mock_inventory ----
    def list_models(self) -> List[Dict[str, Any]]:
        return self._record("mock_inventory.list_models", {}, self._scenario("models", []))

    def check_stock(self, model_code: str, store_id: str) -> Dict[str, Any]:
        model = self._model(model_code)
        if not model:
            raise ValueError(f"unknown model '{model_code}'")
        stock = model.get("stock", {}).get(store_id, 0)
        result = {
            "model_code": model_code,
            "model_name": model.get("name"),
            "store_id": store_id,
            "available": stock,
            "enough_for_demo": stock > 0,
        }
        return self._record("mock_inventory.check_stock", {"model_code": model_code, "store_id": store_id}, result)

    def reserve_car(self, model_code: str, store_id: str) -> Dict[str, Any]:
        result = {
            "status": "reserved",
            "action": "reserve_car",
            "model_code": model_code,
            "store_id": store_id,
            "reservation_id": f"RES-{uuid.uuid4().hex[:6].upper()}",
            "message": "库存预留成功（L1 可逆动作，超时自动释放）。",
        }
        self._action("reserve_car", "L1", {"model_code": model_code, "store_id": store_id})
        return self._record("mock_inventory.reserve_car", {"model_code": model_code, "store_id": store_id}, result)

    # ---- mock_price ----
    def get_policy(self) -> Dict[str, Any]:
        return self._record("mock_price.get_policy", {}, self._policy())

    def calc_quote(self, model_code: str, customer_tier: str) -> Dict[str, Any]:
        model = self._model(model_code)
        if not model:
            raise ValueError(f"unknown model '{model_code}'")
        policy = self._policy()
        guide = float(model.get("guide_price", 0))
        base_discount_pct = float(policy.get("base_discount_pct", 0))
        tier_discount_pct = float(policy.get("tiers", {}).get(customer_tier, 0))
        subsidy = float(model.get("subsidy", 0))
        discount = round(guide * (base_discount_pct + tier_discount_pct) / 100, 2)
        quote = {
            "quote_id": self._make_quote_id(),
            "model_code": model_code,
            "model_name": model.get("name"),
            "guide_price": guide,
            "base_discount": discount,
            "subsidy": subsidy,
            "final_price": round(guide - discount - subsidy, 2),
            "customer_tier": customer_tier,
            "authorized_max_discount_pct": policy.get("authorized_max_discount_pct"),
        }
        self.quotes[quote["quote_id"]] = quote
        return self._record("mock_price.calc_quote", {"model_code": model_code, "customer_tier": customer_tier}, quote)

    def apply_discount(self, quote_id: str, amount: float, reason: str) -> Dict[str, Any]:
        policy = self._policy()
        authorized = float(policy.get("authorized_max_discount_pct", 0))
        quote = self.quotes.get(quote_id)
        if not quote:
            raise ValueError(f"unknown quote '{quote_id}', create a quote with calc_quote first")
        guide_price = float(quote["guide_price"])
        authorized_amount = round(guide_price * authorized / 100, 2)
        if amount <= authorized_amount:
            result = {
                "status": "applied",
                "action": "apply_discount",
                "quote_id": quote_id,
                "amount": amount,
                "authorized_limit": authorized_amount,
                "risk_level": "L1",
                "message": "优惠在授权范围内，已自动应用。",
            }
            self._action("apply_discount", "L1", {"quote_id": quote_id, "amount": amount})
        else:
            approval_id = f"APR-{uuid.uuid4().hex[:6].upper()}"
            self.approvals[approval_id] = {
                "approval_id": approval_id,
                "type": "discount_override",
                "quote_id": quote_id,
                "amount": amount,
                "authorized_limit": authorized_amount,
                "reason": reason,
                "status": "pending",
            }
            result = {
                "status": "needs_approval",
                "action": "apply_discount",
                "quote_id": quote_id,
                "requested_amount": amount,
                "authorized_limit": authorized_amount,
                "risk_level": "L2",
                "approval_id": approval_id,
                "message": "优惠超出授权额度，已生成 L2 审批任务，等待门店经理审批。",
            }
            self._action("apply_discount", "L2", {"quote_id": quote_id, "amount": amount, "approval_id": approval_id})
        return self._record("mock_price.apply_discount", {"quote_id": quote_id, "amount": amount, "reason": reason}, result)

    # ---- mock_finance ----
    def calc_plan(self, price: float, down_payment: float, months: int) -> Dict[str, Any]:
        products = self._scenario("finance", {}).get("products", [])
        plans = []
        for product in products:
            rate = float(product.get("annual_rate_pct", 0)) / 100.0
            loan = max(price - down_payment, 0.0)
            monthly = round((loan * (rate / 12)) / (1 - (1 + rate / 12) ** -months), 2) if months > 0 else loan
            plans.append(
                {
                    "plan_id": f"PLAN-{uuid.uuid4().hex[:6].upper()}",
                    "product": product.get("name"),
                    "loan": round(loan, 2),
                    "down_payment": down_payment,
                    "months": months,
                    "annual_rate_pct": product.get("annual_rate_pct"),
                    "monthly_payment": monthly,
                    "total_interest": round(monthly * months - loan, 2),
                }
            )
        return self._record(
            "mock_finance.calc_plan", {"price": price, "down_payment": down_payment, "months": months},
            {"price": price, "plans": plans},
        )

    def submit_approval(self, plan_id: str, customer_id: str) -> Dict[str, Any]:
        approval_id = f"APR-{uuid.uuid4().hex[:6].upper()}"
        self.approvals[approval_id] = {
            "approval_id": approval_id,
            "type": "credit_authorization",
            "plan_id": plan_id,
            "customer_id": customer_id,
            "status": "pending",
        }
        result = {
            "status": "created",
            "approval_id": approval_id,
            "type": "credit_authorization",
            "risk_level": "L2",
            "message": "征信授权审批任务已创建（涉及个人数据，必须人工审批，审批记录留痕审计）。",
        }
        self._action("submit_credit_approval", "L2", {"plan_id": plan_id, "customer_id": customer_id, "approval_id": approval_id})
        return self._record("mock_finance.submit_approval", {"plan_id": plan_id, "customer_id": customer_id}, result)

    def check_approval(self, approval_id: str) -> Dict[str, Any]:
        approval = self.approvals.get(approval_id)
        if not approval:
            raise ValueError(f"unknown approval '{approval_id}'")
        return self._record("mock_finance.check_approval", {"approval_id": approval_id}, approval)

    # ---- mock_testdrive ----
    def list_slots(self, store_id: str, model_code: str) -> List[Dict[str, Any]]:
        slots = [
            slot
            for slot in self._scenario("testdrive_slots", [])
            if slot.get("store_id") == store_id and slot.get("model_code") == model_code
        ]
        return self._record("mock_testdrive.list_slots", {"store_id": store_id, "model_code": model_code}, slots)

    def book_slot(self, customer_id: str, store_id: str, slot: str, model_code: str) -> Dict[str, Any]:
        slots = [
            s for s in self._scenario("testdrive_slots", [])
            if s.get("store_id") == store_id and s.get("model_code") == model_code and s.get("slot") == slot
        ]
        if not slots:
            raise ValueError(f"slot '{slot}' not available for {model_code} at {store_id}")
        booking_id = f"BK-{uuid.uuid4().hex[:6].upper()}"
        self.bookings[booking_id] = {
            "booking_id": booking_id,
            "customer_id": customer_id,
            "store_id": store_id,
            "slot": slot,
            "model_code": model_code,
            "status": "booked",
        }
        result = {
            "status": "booked",
            "booking_id": booking_id,
            "customer_id": customer_id,
            "store_id": store_id,
            "slot": slot,
            "model_code": model_code,
            "risk_level": "L1",
            "message": "试驾预约成功（L1 自动执行，可随时取消回滚）。",
        }
        self._action("book_testdrive", "L1", {"booking_id": booking_id, "slot": slot, "model_code": model_code})
        return self._record(
            "mock_testdrive.book_slot",
            {"customer_id": customer_id, "store_id": store_id, "slot": slot, "model_code": model_code},
            result,
        )

    def cancel_booking(self, booking_id: str) -> Dict[str, Any]:
        booking = self.bookings.get(booking_id)
        if not booking:
            raise ValueError(f"unknown booking '{booking_id}'")
        booking["status"] = "cancelled"
        result = {
            "status": "cancelled",
            "booking_id": booking_id,
            "message": "试驾预约已取消（回滚完成）。",
        }
        self._action("cancel_booking", "L1", {"booking_id": booking_id})
        return self._record("mock_testdrive.cancel_booking", {"booking_id": booking_id}, result)

    # ---- mock_order ----
    def create_order(self, lead_id: str, quote_id: str, order_key: str) -> Dict[str, Any]:
        # 幂等：相同 order_key 的重复创建直接返回已有订单，防止 Agent 重复下单
        for order in self.orders.values():
            if order.get("order_key") == order_key:
                return self._record("mock_order.create_order", {"lead_id": lead_id, "quote_id": quote_id, "order_key": order_key}, order)
        order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"
        order = {
            "order_id": order_id,
            "order_key": order_key,
            "lead_id": lead_id,
            "quote_id": quote_id,
            "status": "draft",
            "risk_level": "L2",
            "message": "订单草稿已创建。合同与交付属于高风险动作，必须人工审批后进入 confirmed。",
        }
        self.orders[order_id] = order
        self._action("create_order", "L2", {"order_id": order_id, "order_key": order_key, "quote_id": quote_id})
        return self._record(
            "mock_order.create_order", {"lead_id": lead_id, "quote_id": quote_id, "order_key": order_key}, order
        )

    def get_order(self, order_id: str) -> Dict[str, Any]:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"unknown order '{order_id}'")
        return self._record("mock_order.get_order", {"order_id": order_id}, order)

    def rollback_order(self, order_id: str) -> Dict[str, Any]:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"unknown order '{order_id}'")
        order["status"] = "cancelled"
        result = {
            "status": "cancelled",
            "order_id": order_id,
            "rollback_point": "draft",
            "message": "订单已回滚到创建前状态（回滚点：draft），审计记录已保留。",
        }
        self._action("rollback_order", "L1", {"order_id": order_id})
        return self._record("mock_order.rollback_order", {"order_id": order_id}, result)

    # ---- mock_knowledge (RAG) ----
    def search_product(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        docs = self._scenario("knowledge", {}).get("products", [])
        return self._record(
            "mock_knowledge.search_product", {"query": query},
            self._match(docs, query),
        )

    def search_sop(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        docs = self._scenario("knowledge", {}).get("sops", [])
        return self._record("mock_knowledge.search_sop", {"query": query}, self._match(docs, query))

    def search_case(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        docs = self._scenario("knowledge", {}).get("cases", []) + self.saved_cases
        return self._record("mock_knowledge.search_case", {"query": query}, self._match(docs, query))

    def save_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        case = dict(case)
        case["case_id"] = f"CASE-{uuid.uuid4().hex[:6].upper()}"
        case["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.saved_cases.append(case)
        result = {
            "status": "saved",
            "case_id": case["case_id"],
            "message": "成交案例已写入知识库，可被后续 deal-memory 检索复用。",
        }
        self._action("save_case", "L0", {"case_id": case["case_id"]})
        return self._record("mock_knowledge.save_case", {"case": compact(case, 120)}, result)

    @staticmethod
    def _match(docs: List[Dict[str, Any]], query: Optional[str]) -> List[Dict[str, Any]]:
        if not query:
            return docs[:3]
        # 按词拆分（支持空格/逗号分隔），全部命中才返回（AND 语义）
        lowered = query.lower().replace("，", " ").replace(",", " ")
        terms = [term for term in lowered.split() if term]
        hits = []
        for doc in docs:
            text = " ".join(
                str(doc.get(k, "")) for k in ("title", "tags", "summary", "match_terms")
            ).lower()
            if all(term in text for term in terms):
                hits.append(doc)
        return hits[:3]

    # ---- mock_wechat ----
    def get_session(self, customer_id: str) -> Dict[str, Any]:
        sessions = [
            s for s in self._scenario("sessions", [])
            if s.get("channel") == "wechat" and s.get("customer_id") == customer_id
        ]
        result = {"customer_id": customer_id, "sessions": sessions}
        return self._record("mock_wechat.get_session", {"customer_id": customer_id}, result)

    def send_template_message(self, customer_id: str, template: str, params: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "status": "sent",
            "customer_id": customer_id,
            "template": template,
            "params": params,
            "risk_level": "L1",
            "message": "企业微信模板消息已发送（标准话术模板，低风险自动执行）。",
        }
        self._action("send_template_message", "L1", {"customer_id": customer_id, "template": template})
        return self._record(
            "mock_wechat.send_template_message",
            {"customer_id": customer_id, "template": template, "params": params},
            result,
        )

    # ---- mock_verify ----
    def check_deal(self, deal_id: str) -> Dict[str, Any]:
        booked = any(a.get("name") == "book_testdrive" for a in self.actions)
        reserved = any(a.get("name") == "reserve_car" for a in self.actions)
        discount_approval = [a for a in self.actions if a.get("name") == "apply_discount" and a.get("risk_level") == "L2"]
        credit_approval = [a for a in self.actions if a.get("name") == "submit_credit_approval"]
        orders = list(self.orders.values())

        if self.lead_stage == "won":
            status = "won"
            summary = "成交闭环完成：线索状态已流转为成交。"
        elif discount_approval or credit_approval:
            status = "pending_approval"
            summary = "存在待人工审批的高风险动作（大额优惠 / 征信授权），成交挂起等待审批。"
        elif booked or reserved:
            status = "in_progress"
            summary = "低风险动作（试驾预约 / 库存预留）已自动完成，闭环推进中。"
        else:
            status = "in_progress"
            summary = "尚无可验证的执行动作，闭环未启动。"
        return self._record(
            "mock_verify.check_deal",
            {"deal_id": deal_id},
            {
                "deal_id": deal_id,
                "status": status,
                "summary": summary,
                "lead_stage": self.lead_stage,
                "actions_executed": len(self.actions),
                "orders": [
                    {"order_id": o["order_id"], "status": o["status"], "risk_level": o["risk_level"]}
                    for o in orders
                ],
                "approvals_pending": len(self.approvals),
                "low_risk_auto_done": {"testdrive_booked": booked, "car_reserved": reserved},
            },
        )


def max_severity(alerts: Iterable[Dict[str, Any]]) -> str:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    severities = [alert.get("severity", "P4") for alert in alerts]
    return min(severities, key=lambda item: order.get(item, 99), default="P4")
