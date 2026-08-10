from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict
from urllib.parse import unquote, urlparse

from mock_tools import LocalMockTools, list_scenarios


TOOL_STATES: Dict[str, LocalMockTools] = {}


def get_state(scenario_id: str) -> LocalMockTools:
    if scenario_id not in TOOL_STATES:
        TOOL_STATES[scenario_id] = LocalMockTools(scenario_id)
    return TOOL_STATES[scenario_id]


def reset_state(scenario_id: str) -> Dict[str, Any]:
    TOOL_STATES[scenario_id] = LocalMockTools(scenario_id)
    return {"scenario_id": scenario_id, "status": "reset"}


def call_tool(tools: LocalMockTools, name: str, payload: Dict[str, Any]) -> Any:
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
        # 金融审批
        "mock_finance.calc_plan": lambda: tools.calc_plan(float(payload["price"]), float(payload.get("down_payment", 0)), int(payload["months"])),
        "mock_finance.submit_approval": lambda: tools.submit_approval(payload["plan_id"], payload["customer_id"]),
        "mock_finance.check_approval": lambda: tools.check_approval(payload["approval_id"]),
        # 试驾预约
        "mock_testdrive.list_slots": lambda: tools.list_slots(payload["store_id"], payload["model_code"]),
        "mock_testdrive.book_slot": lambda: tools.book_slot(payload["customer_id"], payload["store_id"], payload["slot"], payload["model_code"]),
        "mock_testdrive.cancel_booking": lambda: tools.cancel_booking(payload["booking_id"]),
        # 订单
        "mock_order.create_order": lambda: tools.create_order(payload["lead_id"], payload["quote_id"], payload["order_key"]),
        "mock_order.get_order": lambda: tools.get_order(payload["order_id"]),
        "mock_order.rollback_order": lambda: tools.rollback_order(payload["order_id"]),
        # 知识库 RAG
        "mock_knowledge.search_product": lambda: tools.search_product(payload.get("query")),
        "mock_knowledge.search_sop": lambda: tools.search_sop(payload.get("query")),
        "mock_knowledge.search_case": lambda: tools.search_case(payload.get("query")),
        "mock_knowledge.save_case": lambda: tools.save_case(payload.get("case", payload)),
        # 企业微信
        "mock_wechat.get_session": lambda: tools.get_session(payload["customer_id"]),
        "mock_wechat.send_template_message": lambda: tools.send_template_message(payload["customer_id"], payload["template"], payload.get("params", {})),
        # 闭环验证
        "mock_verify.check_deal": lambda: tools.check_deal(payload["deal_id"]),
    }
    if name not in handlers:
        available = ", ".join(sorted(handlers))
        raise ValueError(f"unknown tool call '{name}', available: {available}")
    return handlers[name]()


class MockToolHandler(BaseHTTPRequestHandler):
    server_version = "SalesFlowMockToolGateway/0.1"

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
                self._send(HTTPStatus.OK, {"ok": True, "service": "salesflow-mock-tool-gateway"})
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
            else:
                result = call_tool(get_state(scenario_id), tool_call, payload)
            self._send(HTTPStatus.OK, {"ok": True, "result": result})
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SalesFlow HTTP mock tool gateway.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=18089, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), MockToolHandler)
    print(f"SalesFlow mock tool gateway listening on http://{args.host}:{args.port}")
    print("Health: GET /health")
    print("Tool call: POST /tools/{scenario_id}/{tool_name}.{function_name}")
    server.serve_forever()


if __name__ == "__main__":
    main()
