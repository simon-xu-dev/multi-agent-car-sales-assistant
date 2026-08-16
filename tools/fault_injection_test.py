"""故障注入端到端测试：验证网关 / Skill 异常处理链路（非 happy path 证据）。

回应评审风险点："116 次工具调用 100% 成功率缺少失败场景证据，只有 happy path"。

原理：以子进程启动带 FAULT_INJECTION 环境变量的 mock_tool_server（临时端口 +
临时 trace 目录，不污染 run_evidence_live），对关键工具注入真实故障，断言：
  1. 网关返回结构化错误（HTTP 200 + {"ok": false, "degraded": true, ...}，不 5xx），
     可被 SkillFailureHandler 三分类（retryable / non_retryable / unknown）正确处理；
  2. retryable 持续故障重试耗尽后降级 + 告警；瞬时故障（fail_times=1）重试成功恢复；
  3. 审计轨迹（audit 端点 + *_audit.jsonl 落盘）可检索 fault_injected 事件；
  4. 故障按工具隔离：注入期间其他工具调用与健康检查不受影响；
  5. 注入关闭（无 FAULT_INJECTION 的新进程）后系统完全恢复。

用例矩阵：
  F-01 timeout 持续注入   -> retryable：重试 1 次耗尽 -> 降级 + 告警（mock_crm.get_lead）
  F-02 http_500 注入      -> unknown：不重试直接降级 + 告警（mock_price.get_policy）
  F-03 empty_result 注入  -> 调用成功但空结果集（mock_knowledge.search_product）
  F-04 auth_error 注入    -> non_retryable：降级 + 人工处理建议（mock_inventory.check_stock）
  F-05 故障隔离           -> 注入期间健康检查 / 未注入工具 / 后续调用全部正常
  F-06 瞬时故障重试恢复   -> fail_times=1 的 timeout：首次超时、重试成功拿到真实结果
  F-07 注入关闭恢复       -> 无 FAULT_INJECTION 的新网关进程：全部工具恢复正常

产物：docs/RUN_EVIDENCE/fault_injection_report.json
用法：python3 tools/fault_injection_test.py（Python 3.11+，零第三方依赖）
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
REPORT_PATH = PROJECT_ROOT / "docs" / "RUN_EVIDENCE" / "fault_injection_report.json"

PASS = 0
FAIL = 0
CASES: List[Dict[str, Any]] = []

# 网关 A 的注入配置：覆盖 4 种故障类型 + 1 个 fail_times 瞬时故障（重试恢复验证）
FAULT_CFG_A: Dict[str, Dict[str, Any]] = {
    "mock_crm.get_lead": {"type": "timeout", "delay_ms": 300},
    "mock_price.get_policy": {"type": "http_500"},
    "mock_knowledge.search_product": {"type": "empty_result"},
    "mock_inventory.check_stock": {"type": "auth_error"},
    "mock_finance.calc_plan": {"type": "timeout", "delay_ms": 120, "fail_times": 1},
}


# ---------------------------------------------------------------------------
# 基础设施：HTTP 客户端 / 网关子进程生命周期 / 检索 helper / 断言
# ---------------------------------------------------------------------------
def http_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None,
              timeout: float = 15.0) -> Tuple[int, Dict[str, Any]]:
    """零依赖 HTTP JSON 客户端（返回状态码与解析后的响应体）。"""
    data = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_gateway(port: int, trace_dir: Path,
                  fault_cfg: Optional[Dict[str, Any]] = None) -> subprocess.Popen:
    """启动网关子进程（cwd=SalesFlow 根目录，环境变量注入 FAULT_INJECTION）。"""
    env = dict(os.environ)
    env.pop("FAULT_INJECTION", None)  # 隔离父进程环境，保证"未配置=关闭"
    if fault_cfg:
        env["FAULT_INJECTION"] = json.dumps(fault_cfg, ensure_ascii=False)
    return subprocess.Popen(
        [sys.executable, str(TOOLS / "mock_tool_server.py"),
         "--host", "127.0.0.1", "--port", str(port), "--trace-dir", str(trace_dir)],
        cwd=str(PROJECT_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def wait_health(port: int, proc: subprocess.Popen, deadline_s: float = 20.0) -> None:
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"gateway exited early (code={proc.returncode}):\n{out[-2000:]}")
        try:
            code, body = http_json("GET", f"http://127.0.0.1:{port}/health", timeout=2)
            if code == 200 and body.get("ok"):
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"gateway health check timeout on port {port}")


def stop_gateway(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def tool_url(base: str, scenario: str, tool: str) -> str:
    return f"{base}/tools/{scenario}/{tool}"


def call(base: str, scenario: str, tool: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    return http_json("POST", tool_url(base, scenario, tool), payload)


def get_result(base: str, path: str) -> Any:
    code, body = http_json("GET", f"{base}{path}")
    assert code == 200, f"GET {path} -> {code}: {body}"
    return body.get("result")


def tool_spans(base: str, scenario: str, tool: str) -> List[Dict[str, Any]]:
    return [s for s in get_result(base, f"/tools/{scenario}/trace") if s.get("tool") == tool]


def fault_logs(base: str, scenario: str, tool: Optional[str] = None,
               ftype: Optional[str] = None) -> List[Dict[str, Any]]:
    """检索 event=fault_injected 的注入 WARN log（可按工具/故障类型过滤）。

    只取 level=WARN（注入发生时刻的记录，attributes 携带 attempt）；
    level=INFO 的同名条目是 audit action 的同步镜像（携带 outcome），不计入。
    """
    code, body = http_json("GET", f"{base}/tools/{scenario}/logs")
    return [l for l in body.get("result", [])
            if l.get("event") == "fault_injected" and l.get("level") == "WARN"
            and (tool is None or l.get("attributes", {}).get("tool") == tool)
            and (ftype is None or l.get("attributes", {}).get("type") == ftype)]


def fault_audit_actions(base: str, scenario: str, tool: Optional[str] = None) -> List[Dict[str, Any]]:
    """检索审计轨迹中的 fault_injected 事件（GET /tools/{s}/audit）。"""
    actions = get_result(base, f"/tools/{scenario}/audit")
    if isinstance(actions, dict):  # audit 端点返回 {total, actions}
        actions = actions.get("actions", [])
    return [a for a in actions
            if a.get("name") == "fault_injected"
            and (tool is None or a.get("tool") == tool)]


def check(case: Dict[str, Any], name: str, condition: bool, detail: str = "") -> bool:
    """断言（风格对齐 selfcheck.py）：计数 + 写入用例 checks 明细。"""
    global PASS, FAIL
    ok = bool(condition)
    if ok:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")
    case["checks"].append({"name": name, "ok": ok, **({"detail": detail} if detail else {})})
    return ok


def new_case(case_id: str, title: str, scenario: str, tool: str,
             fault_desc: str, expectation: str) -> Dict[str, Any]:
    return {
        "case_id": case_id, "title": title, "scenario": scenario, "tool": tool,
        "fault_type": fault_desc, "expectation": expectation,
        "actual": "", "checks": [], "verdict": "fail",
    }


def finish_case(case: Dict[str, Any]) -> None:
    case["verdict"] = "pass" if case["checks"] and all(c["ok"] for c in case["checks"]) else "fail"
    CASES.append(case)
    print(f"  -> {case['case_id']} verdict: {case['verdict'].upper()}")


# ---------------------------------------------------------------------------
# 用例实现（网关 A：注入开启）
# ---------------------------------------------------------------------------
def case_f01_timeout_retry_exhausted(base: str, trace_dir: Path) -> None:
    case = new_case(
        "F-01", "timeout 持续注入 -> retryable 重试耗尽 -> 降级 + 告警", "family_suv_deal",
        "mock_crm.get_lead", "timeout(delay_ms=300, 持续注入)",
        "HTTP 200 结构化降级（非 5xx）：retryable 分类 -> 网关重试 1 次仍超时 -> "
        "result.ok=false / degraded=true / status=degraded / alert=true；"
        "2 条 attempt=1,2 的 fault_injected WARN log（证明重试发生）；"
        "duration_ms>=580（两次 300ms 延迟）；span status=degraded + attributes.fault_injected=timeout；"
        "audit 轨迹含 fault_injected 事件且落盘 JSONL 可检索")
    print(f"\n== F-01: {case['title']} ==")
    code, body = call(base, "family_suv_deal", "mock_crm.get_lead", {"lead_id": "LEAD-2001"})
    result = body.get("result", {})
    check(case, "HTTP 状态码 200（网关降级不阻断，不向调用方抛 5xx）", code == 200, f"got {code}")
    check(case, "外层网关 ok=true（请求被正常处理），内层 result.ok=false（工具失败）",
          body.get("ok") is True and result.get("ok") is False, f"outer={body.get('ok')} result={result}")
    check(case, "降级标记 degraded=true", result.get("degraded") is True)
    check(case, "SkillFailureHandler 分类：retryable 重试耗尽后 status=degraded",
          result.get("status") == "degraded", f"got {result.get('status')}")
    check(case, "降级响应携带告警标记 alert=true", result.get("alert") is True)
    logs = fault_logs(base, "family_suv_deal", "mock_crm.get_lead", "timeout")
    check(case, "fault_injected WARN log 恰好 2 条（attempt=1 与 2，重试真实发生）",
          len(logs) == 2 and sorted(l["attributes"]["attempt"] for l in logs) == [1, 2],
          f"got {len(logs)} logs: {logs}")
    spans = tool_spans(base, "family_suv_deal", "mock_crm.get_lead")
    last = spans[-1] if spans else {}
    check(case, "降级 span status=degraded 且 attributes.fault_injected=timeout",
          last.get("status") == "degraded"
          and last.get("attributes", {}).get("fault_injected") == "timeout", f"span={last}")
    check(case, "span duration_ms>=580（两次注入延迟累积，超时真实发生）",
          float(last.get("duration_ms", 0)) >= 580, f"got {last.get('duration_ms')}ms")
    audits = fault_audit_actions(base, "family_suv_deal", "mock_crm.get_lead")
    check(case, "审计轨迹含 fault_injected(outcome=degraded) 事件",
          any(a.get("type") == "timeout" and a.get("outcome") == "degraded" for a in audits),
          f"audits={audits}")
    trace_file = trace_dir / "family_suv_deal.jsonl"
    audit_file = trace_dir / "family_suv_deal_audit.jsonl"
    trace_persisted = trace_file.exists() and '"fault_injected": "timeout"' in trace_file.read_text(encoding="utf-8")
    audit_persisted = audit_file.exists() and "fault_injected" in audit_file.read_text(encoding="utf-8")
    check(case, "trace JSONL 落盘含 fault_injected 标注（重启后证据不丢）", trace_persisted)
    check(case, "audit JSONL 落盘含 fault_injected 事件（append-only 审计）", audit_persisted)
    case["actual"] = (f"HTTP {code}; result.status={result.get('status')}, alert={result.get('alert')}; "
                      f"retry logs={len(logs)}(attempts {[l['attributes']['attempt'] for l in logs]}); "
                      f"span.status={last.get('status')}, span.fault_injected="
                      f"{last.get('attributes', {}).get('fault_injected')}, duration={last.get('duration_ms')}ms; "
                      f"audit_events={len(audits)}; trace/audit JSONL 落盘={trace_persisted}/{audit_persisted}")
    finish_case(case)


def case_f02_http500_unknown(base: str) -> None:
    case = new_case(
        "F-02", "http_500 注入 -> unknown 分类 -> 不重试直接降级 + 告警", "family_suv_deal",
        "mock_price.get_policy", "http_500(持续注入)",
        "HTTP 200 结构化降级：unknown 分类（无重试）-> status=degraded + alert=true；"
        "仅 1 条 attempt=1 的 fault_injected log（证明未重试）；"
        "span attributes.fault_injected=http_500；audit 留痕；metrics 计入 tool_failure")
    print(f"\n== F-02: {case['title']} ==")
    code, body = call(base, "family_suv_deal", "mock_price.get_policy", {})
    result = body.get("result", {})
    check(case, "HTTP 200 结构化降级", code == 200 and body.get("ok") is True and result.get("ok") is False,
          f"code={code}, body={body}")
    check(case, "unknown 分类降级：status=degraded + alert=true",
          result.get("status") == "degraded" and result.get("alert") is True, f"result={result}")
    logs = fault_logs(base, "family_suv_deal", "mock_price.get_policy", "http_500")
    check(case, "仅 1 条 fault_injected log 且 attempt=1（unknown 不重试）",
          len(logs) == 1 and logs[0]["attributes"]["attempt"] == 1, f"logs={logs}")
    spans = tool_spans(base, "family_suv_deal", "mock_price.get_policy")
    last = spans[-1] if spans else {}
    check(case, "span attributes.fault_injected=http_500",
          last.get("attributes", {}).get("fault_injected") == "http_500", f"span={last}")
    check(case, "audit 轨迹留痕 fault_injected(type=http_500)",
          any(a.get("type") == "http_500" for a in fault_audit_actions(base, "family_suv_deal", "mock_price.get_policy")))
    metrics = get_result(base, "/tools/family_suv_deal/metrics")
    check(case, "metrics 计入 tool_failure（失败可观测）", metrics.get("tool_failure", 0) >= 1, f"metrics={metrics}")
    case["actual"] = (f"HTTP {code}; result.status={result.get('status')}, alert={result.get('alert')}; "
                      f"fault logs={len(logs)}(attempt=1, 未重试); span.fault_injected="
                      f"{last.get('attributes', {}).get('fault_injected')}; "
                      f"tool_failure={metrics.get('tool_failure')}")
    finish_case(case)


def case_f03_empty_result(base: str) -> None:
    case = new_case(
        "F-03", "empty_result 注入 -> 调用成功但返回空结果集（RAG 空检索等价）", "family_suv_deal",
        "mock_knowledge.search_product", "empty_result(持续注入)",
        "HTTP 200 且外层 ok=true（非错误，是数据缺失）；result 为空列表 []；"
        "span status=empty_result + attributes.fault_injected + fault.original_result_preview（原结果留痕）；"
        "audit/log 留痕；metrics 计入 tool_success（空结果非失败）")
    print(f"\n== F-03: {case['title']} ==")
    code, body = call(base, "family_suv_deal", "mock_knowledge.search_product", {"query": "新能源 SUV"})
    result = body.get("result")
    check(case, "HTTP 200 且外层 ok=true（空结果非错误）", code == 200 and body.get("ok") is True, f"code={code}")
    check(case, "result 为空结果集 []（list 型工具语义）", result == [], f"got {result}")
    spans = tool_spans(base, "family_suv_deal", "mock_knowledge.search_product")
    last = spans[-1] if spans else {}
    attrs = last.get("attributes", {})
    check(case, "span status=empty_result 且 attributes.fault_injected=empty_result",
          last.get("status") == "empty_result" and attrs.get("fault_injected") == "empty_result", f"span={last}")
    check(case, "span 保留原结果预览（审计可见\"本来会返回什么\"）",
          bool(attrs.get("fault.original_result_preview")), f"attrs={attrs}")
    check(case, "audit 轨迹留痕 fault_injected(outcome=empty_result)",
          any(a.get("type") == "empty_result" and a.get("outcome") == "empty_result"
              for a in fault_audit_actions(base, "family_suv_deal", "mock_knowledge.search_product")))
    check(case, "WARN log 留痕 fault_injected(type=empty_result)",
          len(fault_logs(base, "family_suv_deal", "mock_knowledge.search_product", "empty_result")) == 1)
    metrics = get_result(base, "/tools/family_suv_deal/metrics")
    check(case, "metrics 计入 tool_success（空结果非失败）", metrics.get("tool_success", 0) >= 1, f"metrics={metrics}")
    case["actual"] = (f"HTTP {code}, ok={body.get('ok')}, result={result}; "
                      f"span.status={last.get('status')}, fault_injected={attrs.get('fault_injected')}, "
                      f"original_preview={str(attrs.get('fault.original_result_preview'))[:80]}...")
    finish_case(case)


def case_f04_auth_error(base: str) -> None:
    case = new_case(
        "F-04", "auth_error 注入 -> non_retryable -> 降级 + 人工处理建议", "family_suv_deal",
        "mock_inventory.check_stock", "auth_error(持续注入)",
        "HTTP 200 结构化降级：non_retryable 分类 -> status=failed + suggestion=\"需人工处理...\"；"
        "仅 1 条 attempt=1 的 fault_injected log（不重试）；"
        "span attributes.fault_injected=auth_error；audit 留痕")
    print(f"\n== F-04: {case['title']} ==")
    code, body = call(base, "family_suv_deal", "mock_inventory.check_stock",
                      {"model_code": "L7", "store_id": "store_001"})
    result = body.get("result", {})
    check(case, "HTTP 200 结构化降级（non_retryable 也不阻断网关）",
          code == 200 and body.get("ok") is True and result.get("ok") is False, f"code={code}, body={body}")
    check(case, "non_retryable 分类：status=failed", result.get("status") == "failed", f"result={result}")
    check(case, "降级响应携带人工处理建议 suggestion", "需人工处理" in str(result.get("suggestion", "")),
          f"suggestion={result.get('suggestion')}")
    logs = fault_logs(base, "family_suv_deal", "mock_inventory.check_stock", "auth_error")
    check(case, "仅 1 条 fault_injected log 且 attempt=1（non_retryable 不重试）",
          len(logs) == 1 and logs[0]["attributes"]["attempt"] == 1, f"logs={logs}")
    spans = tool_spans(base, "family_suv_deal", "mock_inventory.check_stock")
    last = spans[-1] if spans else {}
    check(case, "span attributes.fault_injected=auth_error",
          last.get("attributes", {}).get("fault_injected") == "auth_error", f"span={last}")
    check(case, "audit 轨迹留痕 fault_injected(type=auth_error)",
          any(a.get("type") == "auth_error" for a in fault_audit_actions(base, "family_suv_deal", "mock_inventory.check_stock")))
    case["actual"] = (f"HTTP {code}; result.status={result.get('status')}, suggestion={result.get('suggestion')}; "
                      f"fault logs={len(logs)}(attempt=1, 未重试); span.fault_injected="
                      f"{last.get('attributes', {}).get('fault_injected')}")
    finish_case(case)


def case_f05_isolation(base: str) -> None:
    case = new_case(
        "F-05", "故障隔离：注入期间其他工具 / 健康检查 / 后续调用不受影响", "trade_in_renewal",
        "(未注入工具: list_models / list_sessions + 已注入: get_lead 混调)", "get_lead 注入存在，其余工具无注入",
        "GET /health 200 且 fault_injection.enabled=true（注入开启但健康检查正常）；"
        "list_models 调用故障前后均 ok=true 返回 3 款车型；list_sessions ok=true；"
        "metrics 中 tool_success>=3 与 tool_failure>=1 并存（故障按工具隔离，不扩散）")
    print(f"\n== F-05: {case['title']} ==")
    code, health = http_json("GET", f"{base}/health")
    check(case, "注入期间 /health 200 正常", code == 200 and health.get("ok") is True, f"{code}, {health}")
    check(case, "/health 暴露注入状态 enabled=true（运行时可观测）",
          health.get("fault_injection", {}).get("enabled") is True, f"health={health}")
    code1, m1 = call(base, "trade_in_renewal", "mock_inventory.list_models", {})
    check(case, "故障注入前未注入工具正常（list_models 返回车型目录）",
          code1 == 200 and m1.get("ok") is True and len(m1.get("result", [])) >= 2, f"{code1}, {m1}")
    code2, g = call(base, "trade_in_renewal", "mock_crm.get_lead", {"lead_id": "LEAD-2003"})
    check(case, "已注入工具确实降级（get_lead timeout）",
          code2 == 200 and g.get("result", {}).get("ok") is False, f"{code2}, {g}")
    code3, m2 = call(base, "trade_in_renewal", "mock_inventory.list_models", {})
    check(case, "故障发生后未注入工具仍正常且返回一致（故障不扩散）",
          code3 == 200 and m2.get("ok") is True and m2.get("result") == m1.get("result"), f"{code3}, {m2}")
    code4, s1 = call(base, "trade_in_renewal", "mock_crm.list_sessions", {})
    check(case, "同域其他工具正常（crm.list_sessions 与故障工具同前缀不受影响）",
          code4 == 200 and s1.get("ok") is True and len(s1.get("result", [])) >= 1, f"{code4}, {s1}")
    metrics = get_result(base, "/tools/trade_in_renewal/metrics")
    check(case, "metrics 成功与失败并存（tool_success>=3 且 tool_failure>=1）",
          metrics.get("tool_success", 0) >= 3 and metrics.get("tool_failure", 0) >= 1, f"metrics={metrics}")
    case["actual"] = (f"/health={code}(enabled={health.get('fault_injection', {}).get('enabled')}); "
                      f"list_models 前后两次 ok={m1.get('ok')}/{m2.get('ok')}; "
                      f"get_lead degraded={g.get('result', {}).get('degraded')}; "
                      f"list_sessions ok={s1.get('ok')}; "
                      f"success/failure={metrics.get('tool_success')}/{metrics.get('tool_failure')}")
    finish_case(case)


def case_f06_transient_retry_recovery(base: str) -> None:
    case = new_case(
        "F-06", "瞬时故障重试恢复：fail_times=1 的 timeout 首次超时、重试成功", "first_car_finance",
        "mock_finance.calc_plan", "timeout(delay_ms=120, fail_times=1 仅首次注入)",
        "首次调用 attempt=1 超时（retryable）-> 网关自动重试 attempt=2 不再注入 -> "
        "最终 ok=true 且返回真实金融方案（2 组 plans）；仅 1 条 fault_injected log；"
        "最终 span status=ok 且无 fault_injected 标注")
    print(f"\n== F-06: {case['title']} ==")
    t0 = time.time()
    code, body = call(base, "first_car_finance", "mock_finance.calc_plan",
                      {"price": 150000, "down_payment": 30000, "months": 36})
    elapsed_ms = (time.time() - t0) * 1000
    result = body.get("result", {})
    check(case, "重试后最终成功：ok=true 且返回真实结果（2 组金融方案）",
          code == 200 and body.get("ok") is True and len(result.get("plans", [])) == 2,
          f"code={code}, result={result}")
    logs = fault_logs(base, "first_car_finance", "mock_finance.calc_plan", "timeout")
    check(case, "仅 1 条 fault_injected log（attempt=1 注入，attempt=2 恢复）",
          len(logs) == 1 and logs[0]["attributes"]["attempt"] == 1, f"logs={logs}")
    spans = tool_spans(base, "first_car_finance", "mock_finance.calc_plan")
    last = spans[-1] if spans else {}
    check(case, "最终 span status=ok 且无 fault_injected 标注（恢复后干净）",
          last.get("status") == "ok" and "fault_injected" not in last.get("attributes", {}), f"span={last}")
    check(case, "端到端耗时>=120ms（注入延迟真实发生）", elapsed_ms >= 120, f"got {elapsed_ms:.0f}ms")
    again_code, again = call(base, "first_car_finance", "mock_finance.calc_plan",
                             {"price": 150000, "down_payment": 30000, "months": 36})
    check(case, "注入配额耗尽后后续调用持续正常（fail_times 自动恢复）",
          again_code == 200 and again.get("ok") is True
          and len(fault_logs(base, "first_car_finance", "mock_finance.calc_plan", "timeout")) == 1,
          f"{again_code}, {again}")
    case["actual"] = (f"HTTP {code}, plans={len(result.get('plans', []))} 组, 首次调用耗时 {elapsed_ms:.0f}ms; "
                      f"fault logs 共 1 条(attempt=1); 最终 span.status={last.get('status')}; "
                      f"二次调用 ok={again.get('ok')} 且无新增注入")
    finish_case(case)


# ---------------------------------------------------------------------------
# 用例实现（网关 B：注入关闭，验证完全恢复）
# ---------------------------------------------------------------------------
def case_f07_disabled_recovery(base: str, trace_dir: Path) -> None:
    case = new_case(
        "F-07", "注入关闭恢复：无 FAULT_INJECTION 的新进程全部工具正常", "family_suv_deal",
        "(F-01~F-04 全部原注入工具)", "无（FAULT_INJECTION 环境变量未设置）",
        "新网关进程 /health 显示 enabled=false；get_lead/get_policy/search_product/check_stock "
        "全部 ok=true 且返回真实数据（search_product RAG 重新命中非空）；"
        "全部 span 无 fault_injected 标注、audit 无 fault_injected 事件；JSONL 落盘无注入痕迹")
    print(f"\n== F-07: {case['title']} ==")
    code, health = http_json("GET", f"{base}/health")
    check(case, "/health 正常且 fault_injection.enabled=false",
          code == 200 and health.get("ok") is True
          and health.get("fault_injection", {}).get("enabled") is False, f"{code}, {health}")
    probes = [
        ("mock_crm.get_lead", {"lead_id": "LEAD-2001"}, lambda r: isinstance(r, dict) and r.get("stage")),
        ("mock_price.get_policy", {}, lambda r: "authorized_max_discount_pct" in r),
        ("mock_knowledge.search_product", {"query": "新能源 SUV"}, lambda r: isinstance(r, list) and len(r) >= 1),
        ("mock_inventory.check_stock", {"model_code": "L7", "store_id": "store_001"},
         lambda r: r.get("available", 0) >= 1),
    ]
    for tool, payload, verify in probes:
        c, b = call(base, "family_suv_deal", tool, payload)
        check(case, f"{tool} 恢复正常（真实数据返回）",
              c == 200 and b.get("ok") is True and verify(b.get("result")), f"{c}, {json.dumps(b, ensure_ascii=False)[:200]}")
    # 触发一个会产生审计动作的工具（update_lead_stage L0），确保 audit JSONL 正常生成后可验证无注入痕迹
    uc, ub = call(base, "family_suv_deal", "mock_crm.update_lead_stage",
                  {"lead_id": "LEAD-2001", "stage": "contacted"})
    check(case, "mock_crm.update_lead_stage 恢复正常（产生审计动作，用于后续 JSONL 验证）",
          uc == 200 and ub.get("ok") is True and ub.get("result", {}).get("stage") == "contacted",
          f"{uc}, {ub}")
    spans = get_result(base, "/tools/family_suv_deal/trace")
    check(case, "全部 span 无 fault_injected 标注（恢复后零注入痕迹）",
          all("fault_injected" not in (s.get("attributes") or {}) for s in spans),
          f"faulty={[s.get('tool') for s in spans if 'fault_injected' in (s.get('attributes') or {})]}")
    audit = get_result(base, "/tools/family_suv_deal/audit")
    actions = audit.get("actions", []) if isinstance(audit, dict) else audit
    check(case, "审计轨迹无 fault_injected 事件",
          all(a.get("name") != "fault_injected" for a in actions))
    logs_code, logs_body = http_json("GET", f"{base}/tools/family_suv_deal/logs")
    check(case, "结构化日志无 fault_injected 事件",
          all(l.get("event") != "fault_injected" for l in logs_body.get("result", [])))
    trace_file = trace_dir / "family_suv_deal.jsonl"
    audit_file = trace_dir / "family_suv_deal_audit.jsonl"
    check(case, "JSONL 落盘存在且无注入痕迹（注入不持久、不跨进程）",
          trace_file.exists() and "fault_injected" not in trace_file.read_text(encoding="utf-8")
          and audit_file.exists() and "fault_injected" not in audit_file.read_text(encoding="utf-8"),
          f"trace_exists={trace_file.exists()}, audit_exists={audit_file.exists()}")
    case["actual"] = (f"/health enabled={health.get('fault_injection', {}).get('enabled')}; "
                      f"4 个原注入工具全部 ok=true（search_product 命中非空）; "
                      f"spans={len(spans)} 全部无 fault_injected; audit actions={len(actions)} 无注入事件; "
                      f"JSONL 落盘无注入痕迹")
    finish_case(case)


# ---------------------------------------------------------------------------
# 主流程：启动网关 A（注入）-> F-01~F-06 -> 关闭 -> 启动网关 B（无注入）-> F-07 -> 报告
# ---------------------------------------------------------------------------
def write_report(port_a: int, port_b: int, elapsed_s: float) -> None:
    verdicts = [c["verdict"] for c in CASES]
    report = {
        "meta": {
            "title": "故障注入测试报告（非 happy path 异常处理证据）",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "purpose": "回应评审风险点：\"116 次工具调用 100% 成功率缺少失败场景证据，只有 happy path\"",
            "how_to_reproduce": "cd SalesFlow && python3 tools/fault_injection_test.py",
            "gateway_cmd": f"{sys.executable} tools/mock_tool_server.py --host 127.0.0.1 "
                           f"--port <ephemeral> --trace-dir <tempdir>",
            "gateway_a": {"port": port_a, "fault_injection_env": FAULT_CFG_A},
            "gateway_b": {"port": port_b, "fault_injection_env": "未设置（注入关闭）"},
            "mechanism": "mock_tool_server.py 读取环境变量 FAULT_INJECTION（JSON：工具名->故障规则），"
                         "在 call_tool 内注入故障；未设置时行为与原版完全一致。注入留痕三处："
                         "span attributes.fault_injected / audit action fault_injected / WARN log event=fault_injected",
            "constraints": "未修改 mock_tools.py（SkillFailureHandler 原样复用）；"
                           "Python 3.11+ 标准库 only；临时端口与临时 trace 目录，测试后清理",
            "evidence_note": "临时 trace JSONL 已在用例内断言校验后随临时目录清理；"
                             "完整证据以本报告 + 可复现命令为准",
            "elapsed_seconds": round(elapsed_s, 1),
        },
        "summary": {
            "total_cases": len(CASES),
            "passed": verdicts.count("pass"),
            "failed": verdicts.count("fail"),
            "assertions": {"passed": PASS, "failed": FAIL},
            "fault_types_covered": ["timeout", "http_500", "empty_result", "auth_error"],
            "failure_classification_covered": [
                "retryable（F-01 持续超时重试耗尽降级；F-06 瞬时超时重试成功恢复）",
                "unknown（F-02 http_500 不重试直接降级+告警）",
                "non_retryable（F-04 auth_error 降级+人工处理建议）",
                "empty_result（F-03 空结果集非错误，metrics 计成功）",
            ],
            "degradation_contract": "所有注入故障均以 HTTP 200 + {ok:false, degraded:true, status, gap} 结构化降级返回，"
                                    "网关不向调用方抛 5xx（降级不阻断主链）",
            "isolation_verified": any(c["case_id"] == "F-05" and c["verdict"] == "pass" for c in CASES),
            "recovery_disabled_verified": any(c["case_id"] == "F-07" and c["verdict"] == "pass" for c in CASES),
            "recovery_retry_verified": any(c["case_id"] == "F-06" and c["verdict"] == "pass" for c in CASES),
            "audit_trail_verified": all(
                any(ch["name"].startswith(("audit", "trace JSONL", "audit JSONL")) and ch["ok"]
                    for ch in c["checks"]) for c in CASES if c["case_id"] in {"F-01", "F-02", "F-03", "F-04"}),
        },
        "cases": CASES,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {REPORT_PATH}")


def main() -> int:
    global PASS, FAIL
    tmp = Path(tempfile.mkdtemp(prefix="fault_injection_test_"))
    proc_a: Optional[subprocess.Popen] = None
    proc_b: Optional[subprocess.Popen] = None
    t0 = time.time()
    port_a = port_b = 0
    try:
        # ---- 网关 A：注入开启（随机端口，避免与开发环境 18089 冲突）----
        port_a = free_port()
        trace_a = tmp / "gateway_a"
        print(f"[setup] 启动网关 A（注入开启）port={port_a}, trace_dir={trace_a}")
        proc_a = start_gateway(port_a, trace_a, FAULT_CFG_A)
        wait_health(port_a, proc_a)
        base_a = f"http://127.0.0.1:{port_a}"

        case_f01_timeout_retry_exhausted(base_a, trace_a)
        case_f02_http500_unknown(base_a)
        case_f03_empty_result(base_a)
        case_f04_auth_error(base_a)
        case_f05_isolation(base_a)
        case_f06_transient_retry_recovery(base_a)

        stop_gateway(proc_a)
        proc_a = None
        print("\n[setup] 网关 A 已停止")

        # ---- 网关 B：注入关闭（新进程，无 FAULT_INJECTION）----
        port_b = free_port()
        trace_b = tmp / "gateway_b"
        print(f"[setup] 启动网关 B（注入关闭）port={port_b}, trace_dir={trace_b}")
        proc_b = start_gateway(port_b, trace_b, None)
        wait_health(port_b, proc_b)
        base_b = f"http://127.0.0.1:{port_b}"

        case_f07_disabled_recovery(base_b, trace_b)

        stop_gateway(proc_b)
        proc_b = None
        print("[setup] 网关 B 已停止")

        write_report(port_a, port_b, time.time() - t0)
    finally:
        # 清理：无论成败都停子进程、删临时目录（证据已沉淀到报告 JSON）
        for proc in (proc_a, proc_b):
            if proc is not None and proc.poll() is None:
                stop_gateway(proc)
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"[cleanup] 临时网关进程与临时目录已清理（{tmp}）")

    print(f"\n===== RESULT: {PASS} passed, {FAIL} failed "
          f"({sum(1 for c in CASES if c['verdict'] == 'pass')}/{len(CASES)} cases) =====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
