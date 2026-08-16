from __future__ import annotations

import json
import math
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from vector_rag import DenseRagIndex


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

# 门店别名 -> 场景标准 store_id（真实运行时 LLM 可能从任务文本推断出门店名，需统一归一化）
STORE_ALIASES: Dict[str, List[str]] = {
    "store_001": ["store_001", "hz-binjiang", "杭州滨江旗舰店", "杭州滨江店", "滨江店", "binjiang"],
    "store_002": ["store_002", "sh-hongqiao", "上海虹桥店", "虹桥店", "hongqiao"],
    "store_003": ["store_003", "gz-tianhe", "广州天河店", "天河店", "tianhe"],
}

# 检索停用词：无区分度的高频功能词，分词时忽略，避免稀释信号词
_RAG_STOPWORDS = {
    "的", "了", "在", "吗", "吧", "呢", "想", "要", "请问", "什么", "怎么", "如何",
    "客户", "表示", "提出", "提到", "希望", "需要", "要求", "咨询", "进行", "完成",
    "输出", "结果", "这个", "那个", "一下", "看看", "推荐", "查询", "评估", "计算",
}


class SkillFailureHandler:
    """Skill 失败处理策略（代码级实现，对应 SKILL_ENGINEERING.md §3）。

    在工具网关 call_tool() 中集成：工具调用异常时，按错误类型分类处理，
    保证"降级不阻断"——非致命错误返回结构化降级响应而非抛异常。
    """

    # 可重试错误（瞬时故障：超时/限流/网络抖动）
    RETRYABLE_KEYWORDS = {"timeout", "rate_limit", "transient", "connection", "503", "429"}
    # 不可重试错误（逻辑错误：鉴权/参数/不存在）
    NON_RETRYABLE_KEYWORDS = {"auth", "invalid", "not_found", "permission", "forbidden"}

    @staticmethod
    def classify(error: Exception) -> str:
        """将异常分类为 retryable / non_retryable / unknown。"""
        msg = str(error).lower()
        if any(kw in msg for kw in SkillFailureHandler.RETRYABLE_KEYWORDS):
            return "retryable"
        if any(kw in msg for kw in SkillFailureHandler.NON_RETRYABLE_KEYWORDS):
            return "non_retryable"
        return "unknown"

    @staticmethod
    def handle(tool_name: str, error: Exception, attempt: int = 1) -> Dict[str, Any]:
        """根据错误类型返回结构化降级响应（不抛异常，保证主链不阻断）。

        Returns:
            包含 status/gap/fallback 的字典，调用方可据此判断降级程度。
        """
        error_type = SkillFailureHandler.classify(error)

        if error_type == "retryable" and attempt <= 1:
            # 可重试错误 + 还有重试次数 → 标记需重试
            return {
                "status": "retryable",
                "gap": f"{tool_name} 瞬时故障（{error}），需重试",
                "retry": True,
                "attempt": attempt,
            }

        if error_type == "non_retryable":
            # 不可重试 → 输出证据缺口 + 人工建议
            return {
                "status": "failed",
                "gap": f"{tool_name} 不可用（{error}）",
                "suggestion": f"需人工处理 {tool_name}",
                "retry": False,
            }

        # 重试耗尽 或 未知错误 → 降级 + 告警
        return {
            "status": "degraded",
            "gap": f"{tool_name} 失败（{error}）",
            "fallback": f"{tool_name} 降级输出",
            "alert": True,
            "retry": False,
        }


class TFIDFRagIndex:
    """真向量 RAG：TF-IDF + 余弦相似度（纯 Python 标准库，无第三方依赖）。

    对文档集建立词表与 TF-IDF 向量，查询按余弦相似度排序取 Top-K；低于阈值的返回空
    （语义正确的"无相关文档"，而非硬塞结果）。可替换为 PolarDB pgvector / 任意向量库：
    只需把 _doc_text→embedding、cosine→向量库检索，接口不变。
    """

    def __init__(self, docs: List[Dict[str, Any]], segment_fn: Callable[[str], List[str]],
                 threshold: float = 0.05, top_k: int = 3) -> None:
        self.docs = docs
        self.segment = segment_fn
        self.threshold = threshold
        self.top_k = top_k
        self.doc_tokens = [segment_fn(self._doc_text(d)) for d in docs]
        df: Counter = Counter()
        for toks in self.doc_tokens:
            for t in set(toks):
                df[t] += 1
        n = max(len(docs), 1)
        # idf：平滑处理，避免高频词权重为 0
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        self.doc_vecs = [self._tfidf(toks) for toks in self.doc_tokens]
        self.norms = [self._norm(v) for v in self.doc_vecs]

    @staticmethod
    def _doc_text(d: Dict[str, Any]) -> str:
        parts = [d.get("title", ""), d.get("summary", ""),
                 " ".join(str(t) for t in d.get("tags", [])),
                 " ".join(str(t) for t in d.get("match_terms", []))]
        return " ".join(str(x) for x in parts)

    def _tfidf(self, toks: List[str]) -> Dict[str, float]:
        tf = Counter(toks)
        total = len(toks) or 1
        return {t: (c / total) * self.idf.get(t, 0.0) for t, c in tf.items()}

    @staticmethod
    def _norm(v: Dict[str, float]) -> float:
        return math.sqrt(sum(w * w for w in v.values())) or 1.0

    def search(self, query: Optional[str]) -> List[Dict[str, Any]]:
        if not query:
            return self.docs[: self.top_k]
        qtoks = self.segment(query)
        if not qtoks:
            return self.docs[: self.top_k]
        qvec = self._tfidf(qtoks)
        qnorm = self._norm(qvec)
        scored: List[tuple] = []
        for i, dv in enumerate(self.doc_vecs):
            dot = sum(w * dv.get(t, 0.0) for t, w in qvec.items() if t in dv)
            sim = dot / (qnorm * self.norms[i]) if qnorm and self.norms[i] else 0.0
            if sim >= self.threshold:
                scored.append((sim, i))
        scored.sort(key=lambda x: -x[0])
        return [self.docs[i] for _, i in scored[: self.top_k]]


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

    # OTel GenAI span.kind 语义：RAG 检索归 rag，其余工具调用归 tool
    @staticmethod
    def _span_kind(tool: str) -> str:
        return "rag" if tool.startswith("mock_knowledge") else "tool"

    def __init__(self, scenario_id: str) -> None:
        self.scenario_id = scenario_id
        self.actions: List[Dict[str, Any]] = []
        self.trace: List[Dict[str, Any]] = []
        # 可观测增强（OTel GenAI 风格）：每个场景一个 trace_id，贯穿该场景所有 span/log
        self.trace_id: str = uuid.uuid4().hex
        self.logs: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {
            "tool_calls": 0, "tool_success": 0, "tool_failure": 0,
            "by_tool": {}, "by_kind": {"tool": 0, "rag": 0},
        }

    def _new_span_id(self) -> str:
        return uuid.uuid4().hex[:16]

    def _metric(self, tool: str, ok: bool) -> None:
        m = self.metrics
        m["tool_calls"] += 1
        m["tool_success"] += int(ok)
        m["tool_failure"] += int(not ok)
        m["by_tool"][tool] = m["by_tool"].get(tool, 0) + 1
        kind = self._span_kind(tool)
        m["by_kind"][kind] = m["by_kind"].get(kind, 0) + 1

    def _log(self, event: str, level: str, attributes: Dict[str, Any], span_id: str = "") -> None:
        """结构化 Log：记录决策依据/审批事件/失败原因，通过 trace_id 与 Trace 关联。"""
        self.logs.append({
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "trace_id": self.trace_id,
            "span_id": span_id,
            "level": level,  # INFO / WARN / ERROR
            "event": event,
            "attributes": attributes,
        })

    def _record(self, tool: str, args: Dict[str, Any], result: Any) -> Any:
        span_id = self._new_span_id()
        self.trace.append(
            {
                # 既有字段（向后兼容：selfcheck 与 demo 前端旧 trace 仍可用）
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "tool": tool,
                "args": args,
                "result_preview": compact(result),
                # OTel GenAI 风格 span 字段
                "trace_id": self.trace_id,
                "span_id": span_id,
                "parent_span_id": None,  # 网关层为根 span；Agent 层经 traceparent 传播时可填
                "span_kind": self._span_kind(tool),
                "status": "ok",
                "attributes": {"tool.name": tool},
            }
        )
        self._metric(tool, ok=True)
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
        # 高风险动作（审批/执行/回滚）同步写结构化 Log，供审计与回放
        self._log(
            event=name,
            level="WARN" if risk_level in ("L2", "L3") else "INFO",
            attributes={"risk_level": risk_level, **details},
        )
        return record

    def reset(self) -> None:
        self.actions.clear()
        self.trace.clear()
        self.logs.clear()
        self.metrics = {
            "tool_calls": 0, "tool_success": 0, "tool_failure": 0,
            "by_tool": {}, "by_kind": {"tool": 0, "rag": 0},
        }
        self.trace_id = uuid.uuid4().hex

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

    def confirm_order(self, order_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- mock_approval（人工审批决策：approve / reject / audit）----
    def approve(self, approval_id: str, approver: str = "store_manager", reason: str = "") -> Dict[str, Any]:
        raise NotImplementedError

    def reject(self, approval_id: str, approver: str = "store_manager", reason: str = "") -> Dict[str, Any]:
        raise NotImplementedError

    def audit_trail(self, approval_id: Optional[str] = None, order_id: Optional[str] = None) -> List[Dict[str, Any]]:
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

    def _resolve_store(self, store_id: Optional[str]) -> str:
        """将门店名/别名归一化为场景标准 store_id，避免 LLM 推断名与数据键不匹配。"""
        key = (store_id or "").lower().strip()
        for canonical, aliases in STORE_ALIASES.items():
            if key in (alias.lower() for alias in aliases):
                return canonical
        return store_id or ""

    def check_stock(self, model_code: str, store_id: str) -> Dict[str, Any]:
        model = self._model(model_code)
        if not model:
            raise ValueError(f"unknown model '{model_code}'")
        store_id = self._resolve_store(store_id)
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
        store_id = self._resolve_store(store_id)
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
        store_id = self._resolve_store(store_id)
        slots = [
            slot
            for slot in self._scenario("testdrive_slots", [])
            if slot.get("store_id") == store_id and slot.get("model_code") == model_code
        ]
        return self._record("mock_testdrive.list_slots", {"store_id": store_id, "model_code": model_code}, slots)

    def book_slot(self, customer_id: str, store_id: str, slot: str, model_code: str) -> Dict[str, Any]:
        store_id = self._resolve_store(store_id)
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
        # 关联本单当前所有 pending 审批，使 approve/reject 决策可驱动 confirm/rollback
        approval_refs = [aid for aid, ap in self.approvals.items() if ap.get("status") == "pending"]
        order = {
            "order_id": order_id,
            "order_key": order_key,
            "lead_id": lead_id,
            "quote_id": quote_id,
            "status": "draft",
            "risk_level": "L2",
            "approval_refs": approval_refs,
            "message": "订单草稿已创建。合同与交付属于高风险动作，必须人工审批后进入 confirmed。",
        }
        self.orders[order_id] = order
        self._action("create_order", "L2", {"order_id": order_id, "order_key": order_key, "quote_id": quote_id, "approval_refs": approval_refs})
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
        prev_status = order.get("status", "draft")
        order["status"] = "cancelled"
        result = {
            "status": "cancelled",
            "order_id": order_id,
            "rollback_point": "draft",
            "previous_status": prev_status,
            "message": "订单已回滚到创建前状态（回滚点：draft），审计记录已保留。",
        }
        self._action("rollback_order", "L2", {"order_id": order_id, "previous_status": prev_status})
        return self._record("mock_order.rollback_order", {"order_id": order_id}, result)

    def confirm_order(self, order_id: str) -> Dict[str, Any]:
        """订单 draft -> confirmed：门禁——所有关联审批必须已 approved，且无 rejected。"""
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"unknown order '{order_id}'")
        refs = order.get("approval_refs", [])
        pending = [aid for aid in refs if self.approvals.get(aid, {}).get("status") == "pending"]
        rejected = [aid for aid in refs if self.approvals.get(aid, {}).get("status") == "rejected"]
        if pending:
            result = {
                "status": "blocked",
                "order_id": order_id,
                "blocked_reason": "pending_approvals",
                "pending_approvals": pending,
                "message": "存在未审批的高风险项，订单禁止确认（高风险动作禁止默认放行）。",
            }
            self._action("confirm_order_blocked", "L2", {"order_id": order_id, "pending": pending})
            return self._record("mock_order.confirm_order", {"order_id": order_id}, result)
        if rejected:
            result = {
                "status": "blocked",
                "order_id": order_id,
                "blocked_reason": "rejected_approvals",
                "rejected_approvals": rejected,
                "message": "存在已驳回的高风险项，订单禁止确认，需先回滚。",
            }
            self._action("confirm_order_blocked", "L2", {"order_id": order_id, "rejected": rejected})
            return self._record("mock_order.confirm_order", {"order_id": order_id}, result)
        prev_status = order.get("status", "draft")
        order["status"] = "confirmed"
        result = {
            "status": "confirmed",
            "order_id": order_id,
            "previous_status": prev_status,
            "message": "订单已确认（所有关联审批已通过，合同生效）。",
        }
        self._action("confirm_order", "L2", {"order_id": order_id, "previous_status": prev_status})
        return self._record("mock_order.confirm_order", {"order_id": order_id}, result)

    # ---- mock_approval（人工审批决策）----
    def approve(self, approval_id: str, approver: str = "store_manager", reason: str = "") -> Dict[str, Any]:
        """审批通过：pending -> approved。幂等——重复 approve 返回当前状态。"""
        approval = self.approvals.get(approval_id)
        if not approval:
            raise ValueError(f"unknown approval '{approval_id}'")
        if approval.get("status") != "pending":
            result = {
                "approval_id": approval_id,
                "status": approval["status"],
                "approver": approval.get("decided_by", approver),
                "message": f"审批已决（{approval['status']}），不可重复决策。",
            }
            return self._record("mock_finance.approve", {"approval_id": approval_id, "approver": approver}, result)
        approval["status"] = "approved"
        approval["decided_by"] = approver
        approval["decided_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        approval["decision_reason"] = reason
        result = {
            "approval_id": approval_id,
            "type": approval.get("type"),
            "status": "approved",
            "approver": approver,
            "reason": reason,
            "message": "审批已通过，关联订单可进入 confirm。",
        }
        self._action("approve", "L2", {"approval_id": approval_id, "type": approval.get("type"), "approver": approver, "reason": reason})
        return self._record("mock_finance.approve", {"approval_id": approval_id, "approver": approver}, result)

    def reject(self, approval_id: str, approver: str = "store_manager", reason: str = "") -> Dict[str, Any]:
        """审批驳回：pending -> rejected，并标记关联订单 rollback_requested（不自动回滚，
        由 Agent/Worker 层显式调用 rollback_order 执行，决策与执行分离）。"""
        approval = self.approvals.get(approval_id)
        if not approval:
            raise ValueError(f"unknown approval '{approval_id}'")
        if approval.get("status") != "pending":
            result = {
                "approval_id": approval_id,
                "status": approval["status"],
                "approver": approval.get("decided_by", approver),
                "message": f"审批已决（{approval['status']}），不可重复决策。",
            }
            return self._record("mock_finance.reject", {"approval_id": approval_id, "approver": approver}, result)
        approval["status"] = "rejected"
        approval["decided_by"] = approver
        approval["decided_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        approval["decision_reason"] = reason
        # 标记引用了该审批的订单需回滚（决策层只标记，执行层 rollback_order 真正回滚）
        affected_orders: List[str] = []
        for order in self.orders.values():
            if approval_id in order.get("approval_refs", []):
                order["rollback_requested"] = True
                affected_orders.append(order["order_id"])
        result = {
            "approval_id": approval_id,
            "type": approval.get("type"),
            "status": "rejected",
            "approver": approver,
            "reason": reason,
            "affected_orders": affected_orders,
            "message": "审批已驳回，关联订单已标记 rollback_requested，需由执行层回滚。",
        }
        self._action("reject_approval", "L2", {"approval_id": approval_id, "type": approval.get("type"), "approver": approver, "reason": reason, "affected_orders": affected_orders})
        return self._record("mock_finance.reject", {"approval_id": approval_id, "approver": approver}, result)

    def audit_trail(self, approval_id: Optional[str] = None, order_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """审计轨迹查询：返回结构化 actions（按 approval_id / order_id 可筛选）。

        每个 action 携带 action_id、name、risk_level、time 及关联业务键，
        全量写入 self.logs（通过 trace_id 与 Trace 关联），支持回放与审计。
        """
        actions = list(self.actions)
        if approval_id:
            actions = [a for a in actions if a.get("approval_id") == approval_id]
        if order_id:
            actions = [a for a in actions if a.get("order_id") == order_id]
        return self._record(
            "mock_verify.audit_trail",
            {"approval_id": approval_id, "order_id": order_id},
            {"total": len(actions), "actions": actions},
        )["actions"]

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
    def _segment(query: str) -> List[str]:
        """切分检索词元：中文按 2-gram 滑动切词（无分词库依赖），保留含数字/字母的 token。

        例："成交信号" -> ["成交", "交信", "信号"]，其中"成交"/"信号"可命中数据标签。
        """
        tokens = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9][A-Za-z0-9.%-]*", (query or "").lower())
        terms: List[str] = []
        for token in tokens:
            if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
                terms.extend(token[i : i + 2] for i in range(len(token) - 1))
            else:
                terms.append(token)
        return [t for t in terms if t and t not in _RAG_STOPWORDS]

    @classmethod
    def _match(cls, docs: List[Dict[str, Any]], query: Optional[str]) -> List[Dict[str, Any]]:
        """稠密向量 RAG 检索：DenseRagIndex（字符 n-gram 哈希 → 256 维稠密向量 → 余弦相似度）。

        已从 TF-IDF 稀疏检索升级为 Dense 稠密检索（vector_rag.py DenseRagIndex）。
        Dense 后端通过字符 n-gram 哈希天然支持子串模糊匹配（如"六座SUV" vs "6座suv"），
        对 LLM 自然语言查询的召回率显著优于 TF-IDF。
        后续可平滑迁移到 PolarDB pgvector：替换 _embed() 为模型推理 + search() 为 ANN 检索，
        接口不变。
        """
        return DenseRagIndex(docs, threshold=0.01, top_k=3).search(query, threshold=0.01)

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
        # 审批状态汇总：pending / approved / rejected（驱动成交闭环状态）
        approval_states = [ap.get("status", "pending") for ap in self.approvals.values()]
        pending_count = sum(1 for s in approval_states if s == "pending")
        rejected_count = sum(1 for s in approval_states if s == "rejected")
        approved_count = sum(1 for s in approval_states if s == "approved")
        any_rejected = rejected_count > 0
        any_pending = pending_count > 0
        order_confirmed = any(o.get("status") == "confirmed" for o in orders)
        order_rolled_back = any(o.get("status") == "cancelled" for o in orders)

        if self.lead_stage == "won":
            status = "won"
            summary = "成交闭环完成：线索状态已流转为成交。"
        elif any_rejected or order_rolled_back:
            status = "rolled_back"
            summary = "高风险审批被驳回，关联订单已回滚，闭环安全终止（审计留痕）。"
        elif any_pending:
            status = "pending_approval"
            summary = "存在待人工审批的高风险动作（大额优惠 / 征信授权），成交挂起等待审批。"
        elif approved_count > 0 and order_confirmed:
            status = "won"
            summary = "高风险审批已通过且订单已确认，成交闭环完成。"
        elif approved_count > 0:
            status = "approved"
            summary = "高风险审批已通过，待订单确认后闭环。"
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
                    {"order_id": o["order_id"], "status": o["status"], "risk_level": o.get("risk_level"), "rollback_requested": o.get("rollback_requested", False)}
                    for o in orders
                ],
                "approvals": [
                    {"approval_id": ap.get("approval_id"), "type": ap.get("type"), "status": ap.get("status", "pending"), "decided_by": ap.get("decided_by")}
                    for ap in self.approvals.values()
                ],
                "approvals_pending": pending_count,
                "approvals_approved": approved_count,
                "approvals_rejected": rejected_count,
                "low_risk_auto_done": {"testdrive_booked": booked, "car_reserved": reserved},
            },
        )


def max_severity(alerts: Iterable[Dict[str, Any]]) -> str:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    severities = [alert.get("severity", "P4") for alert in alerts]
    return min(severities, key=lambda item: order.get(item, 99), default="P4")
