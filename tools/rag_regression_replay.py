"""RAG 回归重放：把真实运行 Trace 中返回空结果 `[]` 的 RAG 查询，
通过修复后的 LocalMockTools（加权 OR 检索）重新执行，验证已不再空结果。

背景：2026-08-10 真实 AgentTeams 运行时，mock_knowledge 的检索使用 AND 全词匹配，
导致 LLM 自然语言长句查询大面积返回 `[]`（search_sop "成交信号" / "跟进"、
search_product "新能源六座SUV 25万" 等共 13 条空结果）。事后将 `_match` 改为加权 OR
并补了 selfcheck 回归断言（43/43 通过）。本脚本把真实 Trace 里那些失败查询逐一重放，
作为"修复已验证"的可复现证据，消解"selfcheck 43/43 vs Trace 13 空结果"的矛盾。

用法: python3 tools/rag_regression_replay.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mock_tools import LocalMockTools  # noqa: E402

# 真实运行 Trace 文件 -> 场景 ID 映射
TRACE_TO_SCENARIO = [
    ("docs/RUN_EVIDENCE/DEAL-2001_trace.json", "family_suv_deal", "DEAL-2001"),
    ("docs/RUN_EVIDENCE/deal-2001-trace-run1.json", "family_suv_deal", "DEAL-2001(run1)"),
    ("docs/RUN_EVIDENCE/DEAL-2002_trace_full.json", "first_car_finance", "DEAL-2002"),
    ("docs/RUN_EVIDENCE/DEAL-2003_trace.json", "trade_in_renewal", "DEAL-2003"),
]

RAG_METHODS = {
    "mock_knowledge.search_product": "search_product",
    "mock_knowledge.search_sop": "search_sop",
    "mock_knowledge.search_case": "search_case",
}

EMPTY = "[]"


def load_trace(path: str) -> list:
    d = json.load(open(path, encoding="utf-8"))
    r = d.get("result", d) if isinstance(d, dict) else d
    return r if isinstance(r, list) else []


def replay_one(scenario_id: str, tool: str, query):
    tools = LocalMockTools(scenario_id)
    method = getattr(tools, RAG_METHODS[tool])
    out = method(query)
    return out, tools


def _kb_docs(scenario: dict, tool: str) -> list:
    """该工具对应的知识库文档集合（用于判断查询是否引用了本场景不存在的实体）。"""
    kb = scenario.get("knowledge", {})
    if tool == "mock_knowledge.search_product":
        return kb.get("products", [])
    if tool == "mock_knowledge.search_sop":
        return kb.get("sops", [])
    return kb.get("cases", [])


def _classify_empty(query, tool: str, scenario_id: str) -> str:
    """重放仍空时，判断是'匹配缺陷残留'还是'合法空结果（实体本不存在）'。

    若查询的任一分词在 KB 全量文本中都不出现，说明查询的是本场景知识库根本没有的实体，
    返回 [] 是正确行为，而非匹配缺陷。
    """
    scenario = LocalMockTools(scenario_id).scenario
    docs = _kb_docs(scenario, tool)
    blob = " ".join(
        str(x) for d in docs for x in (
            d.get("title", ""), d.get("summary", ""),
            " ".join(d.get("match_terms", [])),
            " ".join(d.get("tags", [])),
        )
    ).lower()
    terms = LocalMockTools._segment(query or "")
    # 任一分词出现在 KB -> 说明 KB 有相关内容，空结果是匹配缺陷
    has_relevant = any(t in blob for t in terms)
    return "matching_bug_residual" if has_relevant else "legitimate_empty"


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    report = {
        "replay_note": (
            "把真实运行 Trace 中返回 [] 的 RAG 查询，通过修复后的加权 OR 检索重新执行。"
            "区分类别：matching_fixed=原 AND 匹配缺陷、现已命中；"
            "legitimate_empty=查询引用了本场景知识库不存在的实体，返回 [] 属正确行为；"
            "matching_bug_residual=KB 有相关内容仍空，属残留缺陷。"
        ),
        "scenarios": [],
    }
    total_empty = total_matching_fixed = total_legitimate = total_residual = 0

    for rel, scenario_id, deal in TRACE_TO_SCENARIO:
        trace_path = project_root / rel
        if not trace_path.exists():
            continue
        entries = load_trace(str(trace_path))
        empties = [
            e for e in entries
            if e.get("tool") in RAG_METHODS and e.get("result_preview", "").strip() == EMPTY
        ]
        items = []
        for e in empties:
            q = e.get("args", {}).get("query")
            replayed, _ = replay_one(scenario_id, e["tool"], q)
            now_hits = len(replayed) > 0
            if now_hits:
                category = "matching_fixed"
            else:
                category = _classify_empty(q, e["tool"], scenario_id)
            items.append({
                "tool": e["tool"],
                "query": q,
                "before": EMPTY,
                "after_hits": len(replayed),
                "after_titles": [d.get("title", "")[:40] for d in replayed[:3]],
                "category": category,
            })
            total_empty += 1
            if category == "matching_fixed":
                total_matching_fixed += 1
            elif category == "legitimate_empty":
                total_legitimate += 1
            else:
                total_residual += 1

        report["scenarios"].append({
            "deal": deal,
            "scenario_id": scenario_id,
            "trace_file": rel,
            "empty_rag_in_trace": len(empties),
            "matching_fixed": sum(1 for it in items if it["category"] == "matching_fixed"),
            "legitimate_empty": sum(1 for it in items if it["category"] == "legitimate_empty"),
            "matching_bug_residual": sum(1 for it in items if it["category"] == "matching_bug_residual"),
            "items": items,
        })

    report["summary"] = {
        "total_empty_rag_in_real_traces": total_empty,
        "matching_fixed_by_weighted_or": total_matching_fixed,
        "legitimate_empty_entity_absent_from_kb": total_legitimate,
        "matching_bug_residual": total_residual,
        "all_matching_bugs_fixed": total_residual == 0,
    }

    out_path = project_root / "docs" / "RUN_EVIDENCE" / "RAG_regression_replay.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 可读摘要
    print("RAG 回归重放（真实 Trace 空结果查询 × 修复后重放）")
    print("=" * 64)
    for sc in report["scenarios"]:
        print(f"[{sc['deal']}] {sc['trace_file']}  空结果 {sc['empty_rag_in_trace']} 条 "
              f"= 匹配缺陷修复 {sc['matching_fixed']} + 合法空 {sc['legitimate_empty']} + 残留 {sc['matching_bug_residual']}")
        for it in sc["items"]:
            mark = {"matching_fixed": "✓", "legitimate_empty": "○", "matching_bug_residual": "✗"}[it["category"]]
            print(f"  {mark} {it['tool']:32s} q={it['query']!r} [{it['category']}]")
            print(f"      before={it['before']}  after_hits={it['after_hits']}  {it['after_titles']}")
    print("-" * 64)
    s = report["summary"]
    print(f"合计：真实 Trace 空结果 {s['total_empty_rag_in_real_traces']} 条")
    print(f"  匹配缺陷已修复: {s['matching_fixed_by_weighted_or']}")
    print(f"  合法空结果(实体不在KB): {s['legitimate_empty_entity_absent_from_kb']}")
    print(f"  匹配缺陷残留: {s['matching_bug_residual']}")
    print(f"  结论: {'全部匹配缺陷已修复，无残留' if s['all_matching_bugs_fixed'] else '存在残留缺陷'}")
    print(f"证据已写入: {out_path.relative_to(project_root)}")
    return 0 if s["all_matching_bugs_fixed"] else 1


if __name__ == "__main__":
    sys.exit(main())
