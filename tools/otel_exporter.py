"""OTel 真落地：把工具调用 Trace 通过真 OpenTelemetry SDK 导出。

对标赛题"Trace：完整记录 Agent/Skill/MCP/RAG/LLM 等类型 Span，尽量遵循开源语义标准"。
- 用 opentelemetry-sdk 的 TracerProvider + BatchSpanProcessor + ConsoleSpanExporter/FileSpanExporter
- 把 hand-written span dict 重放为真 OTel SDK Span，附加 GenAI semconv 属性
- span_kind 映射：agent/skill→INTERNAL, tool→CLIENT, rag→INTERNAL
- 支持重放 tools/agent_span_builder.py 生成的 Agent→Skill→Tool 三层 trace 树
  （trace_tree_*_20260816.json，agent/skill 层 span + 工具层原始 span）
- 输出：ConsoleSpanExporter 打印真 OTel SDK 格式 Span；FileSpanExporter 落 `docs/RUN_EVIDENCE/otel_sdk_spans.jsonl`

诚实边界：OTel SDK 生成的 span 拥有新的 trace_id/span_id（SDK 内部分配，不可注入）。
原工具网关的 trace_id/span_id 作为 `carsales.original_trace_id` / `carsales.span_id_original` 属性保留，
保证两套 trace 可双向回溯（工具网关 JSON 为审计源真相，OTel SDK 导出为「真 OTel 格式」证据）。

依赖：opentelemetry-api==1.27.0 / opentelemetry-sdk==1.27.0（已验证版本一致）。

用法:
    python3 tools/otel_exporter.py                    # 重放 3 个场景的工具调用 Trace + 三层 trace 树
    python3 tools/otel_exporter.py --trace <file>     # 重放指定 *_trace.json
    python3 tools/otel_exporter.py --tool-traces-only # 仅重放原有工具层 trace（旧行为）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---- OTel SDK imports（已验证版本一致：opentelemetry-api/sdk 1.27.0）----
from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import (  # noqa: E402
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import SpanKind, set_span_in_context  # noqa: E402

# ---- GenAI semconv 属性常量（直接用字符串键，避免 semconv 版本差异）----
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"

LLM_SYSTEM = "dashscope"
DEFAULT_MODEL = "qwen-plus"
SERVICE_NAME = "carsales-agentteams"

EVIDENCE_DIR = PROJECT / "docs" / "RUN_EVIDENCE"
OTEL_SPANS_FILE = EVIDENCE_DIR / "otel_sdk_spans.jsonl"
OTEL_SUMMARY_FILE = EVIDENCE_DIR / "otel_sdk_export_summary.json"


class FileSpanExporter:
    """把真 OTel SDK Span 序列化为 JSONL 落盘（与 ConsoleSpanExporter 并行）。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 每次运行覆盖（fresh evidence）
        self.path.write_text("", encoding="utf-8")
        self.exported: list[dict] = []

    def export(self, spans):  # OTel SDK SpanData 列表
        for sp in spans:
            raw = sp.to_json() if hasattr(sp, "to_json") else json.dumps(
                {"name": sp.name, "span_id": format(sp.context.span_id, "016x")}, default=str
            )
            # to_json 是 pretty-print 多行 JSON → 紧凑成单行，保证 JSONL 每行一 span
            try:
                obj = json.loads(raw)
                line = json.dumps(obj, ensure_ascii=False)
            except Exception:
                line = raw.replace("\n", " ").strip()
                obj = json.loads(line) if line.startswith("{") else {"raw": line}
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self.exported.append(obj)
        return None  # SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _map_kind(span_kind: str) -> SpanKind:
    """工具网关/三层树 span_kind → OTel SpanKind（GenAI 语义：tool=CLIENT，agent/skill/rag=INTERNAL）。"""
    return {
        "agent": SpanKind.INTERNAL,
        "skill": SpanKind.INTERNAL,
        "tool": SpanKind.CLIENT,
        "rag": SpanKind.INTERNAL,
    }.get(span_kind, SpanKind.INTERNAL)


def _enrich_attributes(span: dict) -> dict:
    """给工具网关/三层树 span 的 attributes 补 GenAI semconv 属性。

    诚实：只在已有事实基础上补标准语义键，不编造 LLM 调用记录。
    - agent span: gen_ai.system + gen_ai.agent.name（+ gen_ai.request.model 仅当该 span 真有 LLM 决策）
    - skill span: gen_ai.system + gen_ai.operation.name=invoke_skill（由 agent_span_builder 推导）
    - tool span:  gen_ai.system + gen_ai.tool.name
    - rag span:   gen_ai.system + gen_ai.tool.name（检索器）+ gen_ai.operation.name=rag_query
    """
    attrs = dict(span.get("attributes", {}))
    attrs.setdefault(GEN_AI_SYSTEM, LLM_SYSTEM)
    kind = span.get("span_kind")
    name = span.get("name", "")

    if kind == "agent":
        # agent.name 取 span name 的第一段（如 TeamLeader.approval_gate → TeamLeader）
        agent_name = name.split(".")[0] if "." in name else name
        attrs.setdefault(GEN_AI_AGENT_NAME, agent_name)
        # 仅当该 span 真有 LLM 决策记录（decision_source 属性存在）才标 gen_ai.request.model
        if "decision_source" in attrs or "llm_model" in attrs:
            attrs.setdefault(GEN_AI_REQUEST_MODEL, attrs.get("llm_model", DEFAULT_MODEL))
    elif kind == "skill":
        attrs.setdefault(GEN_AI_OPERATION_NAME, "invoke_skill")
    elif kind == "tool":
        attrs.setdefault(GEN_AI_TOOL_NAME, attrs.get("tool.name", name))
    elif kind == "rag":
        attrs.setdefault(GEN_AI_TOOL_NAME, attrs.get("tool.name", name))
        attrs.setdefault(GEN_AI_OPERATION_NAME, "rag_query")

    # 跨 trace 回溯锚点（OTel SDK 自分配 span_id，原 span_id 落属性保审计）
    attrs.setdefault("carsales.span_id_original", span.get("span_id", ""))
    attrs.setdefault("carsales.parent_span_id_original", span.get("parent_span_id") or "")
    attrs.setdefault("carsales.span_kind_original", span.get("span_kind", ""))
    return attrs


def _setup_provider() -> tuple[Any, "FileSpanExporter"]:
    """构造唯一 TracerProvider + Console/File 双 exporter（全局只设一次）。"""
    provider = TracerProvider(resource=Resource.create({
        "service.name": SERVICE_NAME,
        "service.version": "1.0.0",
        "service.namespace": "carsales",
    }))
    file_exporter = FileSpanExporter(OTEL_SPANS_FILE)
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    provider.add_span_processor(SimpleSpanProcessor(file_exporter))
    trace.set_tracer_provider(provider)  # OTel 全局只允许设一次
    tracer = trace.get_tracer(__name__)
    return tracer, file_exporter, provider


def init_runtime_otel(output_file: str | None = None) -> tuple[Any, "FileSpanExporter", Any] | tuple[None, None, None]:
    """初始化运行时 OTel 插桩（供工具网关在 call_tool 中实时创建真 OTel span）。

    与 _setup_provider() 的区别：
    - 输出文件默认 otel_runtime_spans.jsonl（区分运行时 vs 重放）
    - 不挂 ConsoleSpanExporter（运行时不打印 OTel JSON，避免干扰业务输出）
    - 返回 (tracer, file_exporter, provider)；若 OTel SDK 不可用返回 (None, None, None)

    用法（mock_tool_server.py）:
        tracer, file_exporter, _ = init_runtime_otel()
        # 在 call_tool() 中: otel_span = tracer.start_span(name, ...); otel_span.end()
    """
    try:
        provider = TracerProvider(resource=Resource.create({
            "service.name": SERVICE_NAME,
            "service.version": "1.0.0",
            "service.namespace": "carsales",
            "telemetry.instrumentation": "runtime",  # 标记运行时插桩（非重放）
        }))
        runtime_file = Path(output_file) if output_file else PROJECT / "docs/RUN_EVIDENCE/otel_runtime_spans.jsonl"
        file_exporter = FileSpanExporter(runtime_file)
        # 运行时只用 SimpleSpanProcessor（同步写文件，不异步批处理），保证运行结束前全部落盘
        provider.add_span_processor(SimpleSpanProcessor(file_exporter))
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer(__name__)
        return tracer, file_exporter, provider
    except Exception:
        return None, None, None


def replay_trace(trace_tree: list[dict], tracer, file_exporter: "FileSpanExporter") -> dict:
    """把工具网关 trace 重放为真 OTel SDK Span 并导出。

    返回 {spans_exported, original_trace_id, otel_trace_id, span_kinds, genai_coverage}。
    注意：tracer / file_exporter 由调用方在 main() 中构造一次后复用（OTel 全局 provider 只能设一次）。
    """
    if not trace_tree:
        return {"spans_exported": 0, "error": "empty trace tree"}

    original_trace_id = trace_tree[0].get("trace_id")
    baseline_exported = len(file_exporter.exported)

    # 原 span_id → OTel Span 映射（用于保 parent 链接）
    span_map: dict[str, Any] = {}
    exported = 0

    # trace_tree 已按 time 排序（parent 在前），按序重放即可正确链接 parent
    for sp in trace_tree:
        kind = _map_kind(sp.get("span_kind", "internal"))
        # tool span 用 "tool" 字段而非 "name"，取 name 优先、其次 tool、其次 attributes.tool.name
        name = (sp.get("name") or sp.get("tool")
                or sp.get("attributes", {}).get("tool.name", "unknown"))
        attrs = _enrich_attributes(sp)
        attrs["carsales.original_trace_id"] = original_trace_id or ""

        parent_id = sp.get("parent_span_id")
        ctx = None
        if parent_id and parent_id in span_map:
            ctx = set_span_in_context(span_map[parent_id])

        # start_span 不自动 set as current（replay 场景不需要 contextvar 栈）
        otel_span = tracer.start_span(name, context=ctx, kind=kind, attributes=attrs)
        span_map[sp.get("span_id", "")] = otel_span
        otel_span.end()
        exported += 1

    # 本次重放新增的 span（file_exporter.exported 是累积列表，切片取本次）
    new_exported = file_exporter.exported[baseline_exported:]

    # 统计 GenAI 属性覆盖率 + span kinds（仅本次）
    genai_coverage = sum(
        1 for s in new_exported
        if any(k.startswith("gen_ai.") for k in s.get("attributes", {}))
    )
    span_kinds: dict[str, int] = {}
    otel_trace_id = None
    for s in new_exported:
        k = s.get("kind", "INTERNAL")
        span_kinds[k] = span_kinds.get(k, 0) + 1
        if otel_trace_id is None:
            ctx_obj = s.get("context", {})
            tid = ctx_obj.get("trace_id")
            # ConsoleSpanExporter 的 to_json() 把 trace_id 序列化为 "0x..." 字符串
            otel_trace_id = tid if isinstance(tid, str) else (format(tid, "032x") if isinstance(tid, int) else None)

    return {
        "spans_exported": exported,
        "otel_trace_id": otel_trace_id,
        "original_trace_id": original_trace_id,
        "otel_service_name": SERVICE_NAME,
        "otel_sdk_version": "1.27.0",
        "span_kinds": span_kinds,
        "genai_attribute_spans": genai_coverage,
        "exported_file": str(OTEL_SPANS_FILE.relative_to(PROJECT)),
    }


def _load_trace(path: Path) -> list[dict]:
    """从 *_trace.json 读 trace span 列表（兼容 result / G3_unified_trace / trace / 裸 list 四种格式）。"""
    rec = json.loads(path.read_text(encoding="utf-8"))
    # 工具网关 Trace 文件直接是 span 列表
    if isinstance(rec, list):
        return rec
    # 工具网关 Trace 文件（兼容旧格式：{"ok":..,"result":[..]} / G3_unified_trace / trace）
    if isinstance(rec, dict):
        for key in ("result", "G3_unified_trace", "trace"):
            if isinstance(rec.get(key), list):
                return rec[key]
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description="把工具网关 Trace 通过真 OTel SDK 导出")
    ap.add_argument("--trace", help="指定 *_trace.json 路径（默认重放 3 个场景 trace）")
    ap.add_argument("--tool-traces-only", action="store_true",
                    help="仅重放原有工具层 trace（不重放三层 trace 树，兼容旧行为）")
    args = ap.parse_args()

    print("OTel 真落地（P3.3）：把工具网关 Trace 重放为真 OpenTelemetry SDK Span 导出")
    print("=" * 70)
    print(f"OTel SDK: opentelemetry-api/sdk 1.27.0 | ConsoleSpanExporter + FileSpanExporter")
    print(f"GenAI semconv: gen_ai.system / gen_ai.agent.name / gen_ai.tool.name / gen_ai.request.model")
    print(f"三层树: Agent→Skill→Tool（tools/agent_span_builder.py 生成的 trace_tree_*.json）")
    print()

    if args.trace:
        traces = [Path(args.trace)]
    else:
        traces = [EVIDENCE_DIR / f"DEAL-{i}_trace.json" for i in (2001, 2003)]
        traces += [EVIDENCE_DIR / "DEAL-2002_trace_full.json"]
        if not args.tool_traces_only:
            # 三层 trace 树（agent/skill 层 + 工具层原始 span，存在才重放）
            traces += sorted(EVIDENCE_DIR.glob("trace_tree_*_20260816.json"))

    # 关键：OTel 全局 TracerProvider 只能设一次 → 全程复用单一 provider/tracer/file_exporter
    tracer, file_exporter, provider = _setup_provider()

    all_summaries = []
    for tpath in traces:
        if not tpath.exists():
            print(f"[skip] {tpath} 不存在（先启动工具网关运行场景生成 trace）")
            continue
        trace_tree = _load_trace(tpath)
        print(f"[{tpath.name}] 重放 {len(trace_tree)} 个 span → 真 OTel SDK Span...")
        summary = replay_trace(trace_tree, tracer, file_exporter)
        summary["source_file"] = tpath.name
        # 三层树文件补充层级统计（span_kinds 区分 agent/skill/tool/rag）
        if tpath.name.startswith("trace_tree_"):
            try:
                tree_meta = json.loads(tpath.read_text(encoding="utf-8"))
                if isinstance(tree_meta, dict):
                    summary["span_layers"] = tree_meta.get("span_layers", {})
                    summary["link_integrity"] = tree_meta.get("link_integrity", {})
            except (OSError, json.JSONDecodeError):
                pass  # 统计字段缺失不影响重放本身
        all_summaries.append(summary)
        otel_tid = summary.get("otel_trace_id") or "?"
        orig_tid = summary.get("original_trace_id") or "?"
        print(f"  导出 {summary['spans_exported']} span | OTel trace_id={otel_tid[:16]}... | 原 trace_id={orig_tid[:16]}...")
        print(f"  span_kinds={summary['span_kinds']} | GenAI 属性覆盖 span 数={summary['genai_attribute_spans']}")
        if "span_layers" in summary:
            sl = summary["span_layers"]
            li = summary.get("link_integrity", {})
            print(f"  三层: {sl.get('agent_spans', 0)} agent / {sl.get('skill_spans', 0)} skill / "
                  f"{sl.get('tool_spans', 0)} tool / {sl.get('rag_spans', 0)} rag | "
                  f"工具层挂载率={li.get('tool_span_parented_rate', '?')}")
        print(f"  落盘: {summary['exported_file']}")
        print()

    # 全部 trace 重放完毕后统一 flush + shutdown（BatchSpanProcessor 异步，需显式 flush）
    provider.force_flush()
    provider.shutdown()

    if not all_summaries:
        print("未重放任何 trace。")
        return

    # 全量汇总落盘
    overall = {
        "total_traces_replayed": len(all_summaries),
        "total_spans_exported": sum(s["spans_exported"] for s in all_summaries),
        "otel_sdk_version": "1.27.0",
        "exporters": ["ConsoleSpanExporter", "FileSpanExporter"],
        "genai_semconv_attributes": [
            "gen_ai.system", "gen_ai.agent.name", "gen_ai.tool.name",
            "gen_ai.request.model", "gen_ai.operation.name",
        ],
        "span_layers_total": {
            layer: sum(s.get("span_layers", {}).get(layer, 0) for s in all_summaries)
            for layer in ("agent_spans", "skill_spans", "tool_spans", "rag_spans")
        },
        "honest_boundary": (
            "OTel SDK 生成的 span 拥有 SDK 内部分配的 trace_id/span_id（不可注入）；"
            "原工具网关的 trace_id/span_id 作为 carsales.original_trace_id / carsales.span_id_original 属性保留，"
            "工具网关 JSON 为审计源真相，OTel SDK 导出为「真 OTel 格式」证据，两套可双向回溯。"
            "Agent/Skill 层 span 由 agent_span_builder.py 从 AgentTeams transcript 推导"
            "（derivation=derived_from_transcript，时间范围包住子 span 实际时间戳）。"
        ),
        "per_trace": all_summaries,
    }
    OTEL_SUMMARY_FILE.write_text(json.dumps(overall, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 70)
    print(f"总重放 {overall['total_traces_replayed']} trace / {overall['total_spans_exported']} span")
    print(f"汇总证据: {OTEL_SUMMARY_FILE.relative_to(PROJECT)}")
    print(f"Span JSONL: {OTEL_SPANS_FILE.relative_to(PROJECT)}")
    print("===== OTEL EXPORT: ALL DONE =====")


if __name__ == "__main__":
    main()
