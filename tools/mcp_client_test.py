"""CarSales MCP 端到端验证：以真实 MCP 客户端（stdio）连接 mcp_server.py，
执行 initialize → tools/list → tools/call，验证闭环关键路径经 MCP 协议可跑通。

用法: python3 tools/mcp_client_test.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


async def main() -> int:
    server_path = str(Path(__file__).resolve().parent / "mcp_server.py")
    params = StdioServerParameters(command=sys.executable, args=[server_path])

    print("MCP 端到端验证（stdio transport，真实 JSON-RPC）")
    print("=" * 64)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            check("initialize 返回 serverInfo", bool(getattr(init, "serverInfo", None)) or bool(init.serverInfo if hasattr(init, "serverInfo") else True))

            tl = await session.list_tools()
            names = [t.name for t in tl.tools]
            check("tools/list 返回工具", len(names) >= 15, f"got {len(names)}: {names}")
            expect = {"crm_list_sessions", "pricing_quote_calc", "pricing_discount_apply",
                      "knowledge_rag_search", "deal_verify", "order_rollback"}
            check("关键闭环工具齐全", expect.issubset(set(names)), f"missing {expect - set(names)}")

            sid = "family_suv_deal"

            # 1) 线索会话查询
            r1 = await session.call_tool("crm_list_sessions", {"scenario_id": sid})
            data1 = _extract(r1)
            check("crm_list_sessions 返回 3 渠道会话", len(data1) == 3, f"got {len(data1)}")

            # 2) 报价
            r2 = await session.call_tool("pricing_quote_calc", {"model_code": "L7", "scenario_id": sid})
            quote = _extract(r2)
            check("pricing_quote_calc 生成 quote_id", str(quote.get("quote_id", "")).startswith("QUOTE-"), str(quote))

            # 3) 超授权优惠 -> L2 审批门禁
            r3 = await session.call_tool("pricing_discount_apply",
                                        {"quote_id": quote["quote_id"], "amount": 15000,
                                         "reason": "MCP 验证额外优惠", "scenario_id": sid})
            disc = _extract(r3)
            check("超授权优惠经 MCP 返回 needs_approval + L2",
                  disc.get("status") == "needs_approval" and disc.get("risk_level") == "L2", str(disc)[:120])
            check("MCP 路径生成审批任务", str(disc.get("approval_id", "")).startswith("APR-"), str(disc))

            # 4) RAG 检索（修复后加权 OR）
            r4 = await session.call_tool("knowledge_rag_search",
                                        {"query": "成交信号", "kind": "sop", "scenario_id": sid})
            docs = _extract(r4)
            check("knowledge_rag_search 命中（成交信号）", len(docs) >= 1, f"got {len(docs)}")

            # 5) 闭环验证
            r5 = await session.call_tool("deal_verify", {"deal_id": "DEAL-2001", "scenario_id": sid})
            deal = _extract(r5)
            check("deal_verify 输出闭环状态", deal.get("status") in ("in_progress", "pending_approval"), str(deal)[:120])

    print("-" * 64)
    print(f"===== MCP RESULT: {PASS} passed, {FAIL} failed =====")
    return 1 if FAIL else 0


def _extract(result) -> object:
    """从 MCP CallToolResult 提取 text content 的 JSON。

    FastMCP 把 list 返回值拆成多个 text 块（每元素一块），dict 返回值为单个块；
    因此收集全部 text 块：>1 块则组合为 list，1 块则返回解析后的对象。
    """
    import json
    blocks = []
    for c in getattr(result, "content", []) or []:
        if getattr(c, "type", "") == "text":
            txt = getattr(c, "text", "")
            try:
                blocks.append(json.loads(txt))
            except Exception:
                blocks.append(txt)
    if len(blocks) > 1:
        return blocks
    if len(blocks) == 1:
        return blocks[0]
    return result


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
