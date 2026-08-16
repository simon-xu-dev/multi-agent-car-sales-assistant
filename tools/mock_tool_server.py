from __future__ import annotations

import argparse
import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from mock_tools import LocalMockTools, SkillFailureHandler, SMS_ALERT_SKILL, compact, list_scenarios
from evidence_archive import EvidenceArchiveSkill


TOOL_STATES: Dict[str, LocalMockTools] = {}
TRACE_DIR: Path = Path("run_evidence_live")
ARCHIVE = EvidenceArchiveSkill()  # 证据归档 Skill 单例（有 OSS 凭证真调 REST，无凭证降级本地 bucket）
# 审计轨迹追加落盘的偏移（按 scenario 记录已写入 actions 数量，仅追加新增项，幂等）
_AUDIT_OFFSET: Dict[str, int] = {}

# ---------------------------------------------------------------------------
# 故障注入（测试专用，默认关闭）：回应"工具调用 100% 成功率只有 happy path"的评审风险点。
#
# 通过环境变量 FAULT_INJECTION 传入 JSON 配置（工具名 -> 故障规则），在网关层对
# 匹配的工具调用注入真实故障，验证 SkillFailureHandler 三分类（retryable /
# non_retryable / unknown）与"降级不阻断"链路。未设置该环境变量时注入完全关闭，
# 行为与原版一致（每次调用仅多一次 dict 查找，零行为差异）。
#
# 注入行为全量留痕（三处，均可检索审计）：
#   1. span attributes.fault_injected（GET /tools/{s}/trace）
#   2. audit action "fault_injected"（GET /tools/{s}/audit + *_audit.jsonl 落盘）
#   3. 结构化 WARN log event=fault_injected（GET /tools/{s}/logs，trace_id 关联）
#
# 配置 schema（值为字符串时等价 {"type": <字符串>}）：
#   {
#     "mock_crm.get_lead":             {"type": "timeout", "delay_ms": 300},
#     "mock_price.get_policy":         {"type": "http_500"},
#     "mock_knowledge.search_product": {"type": "empty_result"},
#     "mock_finance.calc_plan":        {"type": "auth_error", "fail_times": 1}
#   }
#
# 故障类型与预期分类（SkillFailureHandler 关键词匹配，见 mock_tools.py）：
#   timeout      —— 延迟 delay_ms 后抛超时异常（含 "timeout" → retryable：
#                   网关重试 1 次；持续注入时重试耗尽 → 降级 + 告警）
#   http_500     —— 抛上游 500 异常（不含分类关键词 → unknown：不重试，直接降级 + 告警）
#   empty_result —— 调用成功但返回空结果集（模拟 RAG 空检索/数据缺失，非错误）
#   auth_error   —— 抛鉴权异常（含 "auth"/"permission" → non_retryable：降级 + 人工建议）
#
# 可选参数：
#   delay_ms    timeout 注入前的真实延迟毫秒数（默认 100）
#   fail_times  仅前 N 次调用注入，之后自动恢复（默认 -1 持续注入）；
#               用于验证 retryable 瞬时故障的"重试后恢复"路径
# ---------------------------------------------------------------------------
FAULT_TYPES = {"timeout", "http_500", "empty_result", "auth_error"}
_FAULT_INJECTED_COUNT: Dict[str, int] = {}  # 每工具已注入次数（fail_times 恢复判断）


class FaultInjectionError(RuntimeError):
    """故障注入异常（测试专用）。

    message 保持真实故障语义（含 SkillFailureHandler 分类关键词，不伪装分类结果），
    附带 fault_type / tool 元数据，供降级 span 标注与审计轨迹留痕。
    """

    def __init__(self, message: str, fault_type: str, tool: str) -> None:
        super().__init__(message)
        self.fault_type = fault_type
        self.tool = tool


def _load_fault_rules() -> Dict[str, Dict[str, Any]]:
    """解析环境变量 FAULT_INJECTION（JSON：工具名 -> 故障规则）。

    未设置或为空 → 返回 {}（注入完全关闭）；配置非法 → 启动即失败（fail fast，
    避免测试在"以为注入了其实没有"的假象下静默通过）。
    """
    raw = os.environ.get("FAULT_INJECTION", "")
    if not raw.strip():
        return {}
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"FAULT_INJECTION is not valid JSON: {exc}") from exc
    if not isinstance(cfg, dict):
        raise ValueError("FAULT_INJECTION must be a JSON object like {tool_name: fault_spec}")
    rules: Dict[str, Dict[str, Any]] = {}
    for name, spec in cfg.items():
        rule = {"type": spec} if isinstance(spec, str) else dict(spec)
        ftype = rule.get("type")
        if ftype not in FAULT_TYPES:
            raise ValueError(f"unknown fault type '{ftype}' for '{name}', available: {sorted(FAULT_TYPES)}")
        rules[name] = rule
    return rules


_FAULT_RULES = _load_fault_rules()


def _check_fault(name: str) -> Optional[Dict[str, Any]]:
    """按规则判定本次调用是否注入故障（含 fail_times 自动恢复判断）。

    返回规则 dict（注入）或 None（不注入）。注入即计数，供 fail_times 恢复。
    """
    rule = _FAULT_RULES.get(name)
    if not rule:
        return None
    fail_times = int(rule.get("fail_times", -1))
    if fail_times >= 0 and _FAULT_INJECTED_COUNT.get(name, 0) >= fail_times:
        return None  # 已注入满 N 次，自动恢复（验证重试恢复路径）
    _FAULT_INJECTED_COUNT[name] = _FAULT_INJECTED_COUNT.get(name, 0) + 1
    return rule


def _raise_fault(name: str, rule: Dict[str, Any]) -> None:
    """构造并抛出注入异常（timeout 型先真实延迟 delay_ms 模拟慢上游）。"""
    ftype = rule["type"]
    if ftype == "timeout":
        delay_ms = int(rule.get("delay_ms", 100))
        time.sleep(delay_ms / 1000.0)
        raise FaultInjectionError(
            f"upstream '{name}' timeout after {delay_ms}ms (fault-injected)", ftype, name)
    if ftype == "http_500":
        raise FaultInjectionError(
            f"upstream '{name}' returned HTTP 500 internal server error (fault-injected)", ftype, name)
    raise FaultInjectionError(  # auth_error
        f"upstream '{name}' auth token expired, permission denied (fault-injected)", ftype, name)


def _apply_empty_result(tools: LocalMockTools, name: str, result: Any) -> Any:
    """empty_result 注入：调用成功但返回空结果集（模拟 RAG 空检索，非错误）。

    响应体保持真实世界的空结果语义（list -> []，dict -> {"results": []}），
    注入痕迹留存在可观测层：span status=empty_result + attributes、audit action、
    WARN log；原结果预览保留在 attributes.fault.original_result_preview（审计可见
    "本来会返回什么"）。
    """
    replaced: Any = [] if isinstance(result, list) else {"results": []}
    if tools.trace and tools.trace[-1].get("tool") == name:
        span = tools.trace[-1]
        span["status"] = "empty_result"
        span.setdefault("attributes", {})["fault_injected"] = "empty_result"
        span["attributes"]["fault.original_result_preview"] = compact(result)
    tools._action("fault_injected", "L0",
                  {"tool": name, "type": "empty_result", "outcome": "empty_result",
                   "original_result_preview": compact(result)})
    tools._log(event="fault_injected", level="WARN", attributes={"tool": name, "type": "empty_result"})
    return replaced


def persist_last_trace(scenario_id: str) -> None:
    """将最近一次工具调用 Trace 追加落盘（JSONL），重启后证据不丢失。"""
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    tools = get_state(scenario_id)
    record = tools.trace[-1]
    with (TRACE_DIR / f"{scenario_id}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    # 审计轨迹：仅追加本场景新增的 actions（幂等偏移），形成 append-only 审计日志
    offset = _AUDIT_OFFSET.get(scenario_id, 0)
    new_actions = tools.actions[offset:]
    if new_actions:
        with (TRACE_DIR / f"{scenario_id}_audit.jsonl").open("a", encoding="utf-8") as f:
            for a in new_actions:
                f.write(json.dumps({"trace_id": tools.trace_id, **a}, ensure_ascii=False) + "\n")
        _AUDIT_OFFSET[scenario_id] = len(tools.actions)


def get_state(scenario_id: str) -> LocalMockTools:
    if scenario_id not in TOOL_STATES:
        TOOL_STATES[scenario_id] = LocalMockTools(scenario_id)
    return TOOL_STATES[scenario_id]


def reset_state(scenario_id: str) -> Dict[str, Any]:
    TOOL_STATES[scenario_id] = LocalMockTools(scenario_id)
    _AUDIT_OFFSET[scenario_id] = 0  # 重置审计偏移，配合新会话重放
    return {"scenario_id": scenario_id, "status": "reset"}


def _parse_traceparent(header: Optional[str]) -> Optional[tuple[str, str]]:
    """W3C traceparent: version-trace_id-parent_id-flags。返回 (trace_id, parent_id)（Agent 层 span）。

    trace_id 用于让工具 span 归属同一分布式 trace（OTel 语义：同一 trace 的所有 span 共享 trace_id），
    parent_id 作为 parent_span_id 把 Agent 层 span 链为工具 span 的父节点，形成完整 trace 树。
    """
    if not header:
        return None
    parts = header.strip().split("-")
    if len(parts) >= 3 and len(parts[1]) == 32 and len(parts[2]) == 16:
        return parts[1], parts[2]
    return None


def call_tool(
    tools: LocalMockTools, name: str, payload: Dict[str, Any],
    parent_span_id: Optional[str] = None, trace_id: Optional[str] = None,
) -> Any:
    handlers: Dict[str, Callable[[], Any]] = {
        # CRM 客户关系
        "mock_crm.get_lead": lambda: tools.get_lead(payload.get("lead_id")),
        "mock_crm.list_sessions": lambda: tools.list_sessions(),
        "mock_crm.get_customer_history": lambda: tools.get_customer_history(payload.get("customer_id")),
        "mock_crm.update_lead_stage": lambda: tools.update_lead_stage(payload["lead_id"], payload["stage"]),
        # 库存 / DMS
        "mock_inventory.list_models": lambda: tools.list_models(),
        "mock_inventory.check_stock": lambda: tools.check_stock(payload["model_code"], payload["store_id"]),
        "mock_inventory.reserve_car": lambda: tools.reserve_car(payload["model_code"], payload["store_id"]),
        # 报价与优惠
        "mock_price.get_policy": lambda: tools.get_policy(),
        "mock_price.calc_quote": lambda: tools.calc_quote(payload["model_code"], payload.get("customer_tier", "normal")),
        "mock_price.apply_discount": lambda: tools.apply_discount(payload["quote_id"], float(payload["amount"]), payload.get("reason", "")),
        # 置换评估（置换+金融复合场景 DEAL-2004）
        "mock_tradein.assess_vehicle": lambda: tools.assess_vehicle(payload.get("old_model", ""), int(payload.get("mileage_km", 0))),
        "mock_tradein.request_uplift": lambda: tools.request_uplift(payload["assessment_id"], float(payload["requested_offer"]), payload.get("reason", "")),
        # 金融审批
        "mock_finance.calc_plan": lambda: tools.calc_plan(float(payload["price"]), float(payload.get("down_payment", 0)), int(payload["months"])),
        "mock_finance.submit_approval": lambda: tools.submit_approval(payload["plan_id"], payload["customer_id"]),
        "mock_finance.check_approval": lambda: tools.check_approval(payload["approval_id"]),
        # 人工审批决策（approve/reject 驱动 confirm/rollback 闭环）
        "mock_finance.approve": lambda: tools.approve(payload["approval_id"], payload.get("approver", "store_manager"), payload.get("reason", "")),
        "mock_finance.reject": lambda: tools.reject(payload["approval_id"], payload.get("approver", "store_manager"), payload.get("reason", "")),
        # 试驾预约
        "mock_testdrive.list_slots": lambda: tools.list_slots(payload["store_id"], payload["model_code"]),
        "mock_testdrive.book_slot": lambda: tools.book_slot(payload["customer_id"], payload["store_id"], payload["slot"], payload["model_code"]),
        "mock_testdrive.cancel_booking": lambda: tools.cancel_booking(payload["booking_id"]),
        # 订单
        "mock_order.create_order": lambda: tools.create_order(payload["lead_id"], payload["quote_id"], payload["order_key"]),
        "mock_order.get_order": lambda: tools.get_order(payload["order_id"]),
        "mock_order.rollback_order": lambda: tools.rollback_order(payload["order_id"]),
        "mock_order.confirm_order": lambda: tools.confirm_order(payload["order_id"]),
        # 知识库 RAG
        "mock_knowledge.search_product": lambda: tools.search_product(payload.get("query")),
        "mock_knowledge.search_sop": lambda: tools.search_sop(payload.get("query")),
        "mock_knowledge.search_case": lambda: tools.search_case(payload.get("query")),
        "mock_knowledge.save_case": lambda: tools.save_case(payload.get("case", payload)),
        # 企业微信
        "mock_wechat.get_session": lambda: tools.get_session(payload["customer_id"]),
        "mock_wechat.send_template_message": lambda: tools.send_template_message(payload["customer_id"], payload["template"], payload.get("params", {})),
        # 审批告警短信（官方用云 Skill：阿里云短信，L2 门禁 needs_approval 时触达审批人）
        "mock_sms.send_approval_alert": lambda: tools.send_approval_alert(
            payload["approval_id"], payload.get("deal_id", ""), payload.get("risk_type", ""),
            payload.get("summary", ""), payload.get("approver", "store_manager")),
        # 闭环验证
        "mock_verify.check_deal": lambda: tools.check_deal(payload["deal_id"]),
        "mock_verify.audit_trail": lambda: tools.audit_trail(payload.get("approval_id"), payload.get("order_id")),
    }
    if name not in handlers:
        available = ", ".join(sorted(handlers))
        raise ValueError(f"unknown tool call '{name}', available: {available}")

    t0 = time.time()
    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt <= 1:
        attempt += 1
        try:
            rule = _check_fault(name)
            if rule is not None and rule["type"] != "empty_result":
                # 注入真实故障（timeout 型先真实延迟）：异常走下方统一的分类/重试/降级链路
                tools._log(event="fault_injected", level="WARN",
                           attributes={"tool": name, "type": rule["type"], "attempt": attempt})
                _raise_fault(name, rule)
            result = handlers[name]()
            if rule is not None and rule["type"] == "empty_result":
                result = _apply_empty_result(tools, name, result)
            break
        except Exception as exc:
            last_exc = exc
            failure = SkillFailureHandler.handle(name, exc, attempt=attempt)
            if failure.get("retry"):
                # 可重试错误（超时/限流），重试一次
                continue
            # 不可重试 或 重试耗尽 → 降级响应（不抛异常，保证主链不阻断）
            duration_ms = round((time.time() - t0) * 1000, 2)
            span_id = tools._new_span_id()
            tools.trace.append({
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "tool": name, "args": payload, "result_preview": f"DEGRADED: {failure['gap']}",
                "trace_id": trace_id or tools.trace_id, "span_id": span_id, "parent_span_id": parent_span_id,
                "span_kind": tools._span_kind(name), "status": "degraded",
                "duration_ms": duration_ms,
                "attributes": {"tool.name": name, "error.message": str(exc),
                               "failure.status": failure["status"], "failure.gap": failure["gap"]},
            })
            if isinstance(exc, FaultInjectionError):
                # 注入故障留痕：降级 span 标注 + 审计轨迹事件（audit 端点/JSONL 可检索 fault_injected）
                tools.trace[-1]["attributes"]["fault_injected"] = exc.fault_type
                tools._action("fault_injected", "L0",
                              {"tool": name, "type": exc.fault_type, "outcome": "degraded"})
            if trace_id:
                tools.trace[-1]["attributes"]["gateway.session_id"] = tools.trace_id
            tools._metric(name, ok=False)
            tools._log(event="tool_call_degraded", level="WARN",
                       attributes={"tool": name, **failure}, span_id=span_id)
            return {"ok": False, "degraded": True, **failure}
    else:
        # while 正常结束（不应到达），兜底
        raise last_exc  # pragma: no cover
    # 成功路径：方法内已 _record 追加 span，这里补 duration_ms / parent_span_id / 传播 trace_id
    duration_ms = round((time.time() - t0) * 1000, 2)
    if tools.trace and tools.trace[-1].get("tool") == name and tools.trace[-1].get("status") == "ok":
        tools.trace[-1]["duration_ms"] = duration_ms
        tools.trace[-1]["parent_span_id"] = parent_span_id
        if trace_id:
            # 采用传播的分布式 trace_id，让工具 span 与 Agent 层 span 同属一个 trace；
            # 网关会话 id 作为属性保留，便于与 /metrics（会话级）关联。
            tools.trace[-1]["trace_id"] = trace_id
            tools.trace[-1].setdefault("attributes", {})["gateway.session_id"] = tools.trace_id
    return result


class MockToolHandler(BaseHTTPRequestHandler):
    server_version = "CarSalesMockToolGateway/0.1"

    def _send(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        try:
            if parts == ["health"]:
                self._send(HTTPStatus.OK, {
                    "ok": True, "service": "carsales-mock-tool-gateway",
                    "fault_injection": {"enabled": bool(_FAULT_RULES), "rules": sorted(_FAULT_RULES)},
                })
                return
            if parts == ["scenarios"]:
                self._send(HTTPStatus.OK, {"ok": True, "result": list_scenarios()})
                return
            if len(parts) == 4 and parts[0] == "tools" and parts[2] == "tools" and parts[3] == "trace":
                tools = get_state(parts[1])
                self._send(HTTPStatus.OK, {"ok": True, "result": tools.trace})
                return
            if len(parts) == 3 and parts[0] == "tools" and parts[2] == "trace":
                tools = get_state(parts[1])
                self._send(HTTPStatus.OK, {"ok": True, "result": tools.trace})
                return
            if len(parts) == 3 and parts[0] == "tools" and parts[2] == "logs":
                tools = get_state(parts[1])
                self._send(HTTPStatus.OK, {"ok": True, "trace_id": tools.trace_id, "result": tools.logs})
                return
            if len(parts) == 3 and parts[0] == "tools" and parts[2] == "metrics":
                tools = get_state(parts[1])
                m = dict(tools.metrics)
                calls = m.get("tool_calls", 0)
                m["trace_id"] = tools.trace_id
                m["tool_success_rate"] = round(m["tool_success"] / calls, 4) if calls else 0.0
                self._send(HTTPStatus.OK, {"ok": True, "result": m})
                return
            if len(parts) == 3 and parts[0] == "tools" and parts[2] == "audit":
                # 审计轨迹：结构化 actions（按 approval_id / order_id 可选筛选）
                tools = get_state(parts[1])
                q = parse_qs(parsed.query)
                approval_id = q.get("approval_id", [None])[0]
                order_id = q.get("order_id", [None])[0]
                actions = tools.audit_trail(approval_id, order_id)
                self._send(HTTPStatus.OK, {"ok": True, "trace_id": tools.trace_id,
                                           "result": {"total": len(actions), "actions": actions}})
                return
            if len(parts) == 3 and parts[0] == "tools" and parts[2] == "archives":
                # 列出已归档证据（按 trace_id 回溯审计）
                self._send(HTTPStatus.OK, {"ok": True, "result": ARCHIVE.list_archives(parts[1])})
                return
            self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown endpoint"})
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        try:
            if len(parts) != 3 or parts[0] != "tools":
                self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "expected /tools/{scenario_id}/{tool_call}"})
                return
            scenario_id, tool_call = parts[1], parts[2]
            payload = self._read_json()
            if tool_call == "reset":
                result = reset_state(scenario_id)
                with (TRACE_DIR / f"{scenario_id}.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"event": "reset", "time": result.get("status")}, ensure_ascii=False) + "\n")
            elif tool_call == "archive":
                # 证据归档 Skill：快照 trace+log+metrics 到对象存储（OSS 等价），异步不阻塞主链
                tools = get_state(scenario_id)
                deal_id = payload.get("deal_id", "DEAL-UNKNOWN")
                result = ARCHIVE.archive_run(
                    scenario_id, deal_id, tools.trace_id, tools.trace, tools.logs, tools.metrics)
                tools._log(event="evidence_archived", level="INFO",
                           attributes={"object_key": result["object_key"], "etag": result["etag"],
                                       "store_type": result.get("store_type", "local")})
            else:
                # W3C traceparent 传播：Agent 层 span 作为工具 span 的 parent，trace_id 让二者同属一个 trace
                prop = _parse_traceparent(self.headers.get("traceparent"))
                p_tid, p_pid = prop if prop else (None, None)
                try:
                    result = call_tool(get_state(scenario_id), tool_call, payload, p_pid, p_tid)
                except Exception:
                    persist_last_trace(scenario_id)  # error span 同样落盘，证据完整
                    raise
                persist_last_trace(scenario_id)
            self._send(HTTPStatus.OK, {"ok": True, "result": result})
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CarSales HTTP mock tool gateway.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=18089, type=int)
    parser.add_argument("--trace-dir", default="run_evidence_live", help="trace JSONL 持久化目录（重启不丢）")
    args = parser.parse_args()
    global TRACE_DIR
    TRACE_DIR = Path(args.trace_dir)
    TRACE_DIR.mkdir(parents=True, exist_ok=True)  # 首次运行即创建，reset 分支直接 open 不再崩
    # 短信外呼记录与 trace/audit 同目录落盘（--trace-dir 统一控制，证据不散落）
    SMS_ALERT_SKILL.out_dir = TRACE_DIR

    server = ThreadingHTTPServer((args.host, args.port), MockToolHandler)
    print(f"CarSales mock tool gateway listening on http://{args.host}:{args.port}")
    if _FAULT_RULES:
        print(f"FAULT INJECTION ENABLED: {json.dumps(_FAULT_RULES, ensure_ascii=False)}")
    else:
        print("Fault injection: disabled (set FAULT_INJECTION env to enable)")
    print("Health: GET /health")
    print("Tool call: POST /tools/{scenario_id}/{tool_name}.{function_name}")
    print(f"Trace persistence: {TRACE_DIR}/{{scenario_id}}.jsonl")
    server.serve_forever()


if __name__ == "__main__":
    main()
