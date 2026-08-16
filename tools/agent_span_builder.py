"""Agent → Skill → Tool 三层全链路 Trace 构建器（可观测补全，任务 #2）。

对标赛题「Trace：完整记录 Agent / Skill / MCP / RAG / LLM 等类型 Span」。
当前短板：工具网关 trace 只覆盖工具调用层 span，所有工具 span 的 parent_span_id 均为 null。
本构建器从真实运行证据推导上层 span，补全三层 trace 树：

- Agent 层 span：从 AgentTeams Matrix transcript（agentteams_20260816_transcript.json）推导
  8 个 Worker + TeamLeader 的执行时间范围 / 状态 / 产出（消息时间戳为真实数据，不伪造）。
- Skill 层 span：根据 skill_registry.json 的 owner_agent + depends_on_tools，把工具调用
  归组为「连续同 skill 执行段」，每段一个 skill span。
- Tool 层 span：复用工具网关 trace_*_20260816.json 的原始 span（原 span_id / duration /
  result_preview 原样保留），仅回填 parent_span_id 完成挂载。

工具 span → Agent 的归属判定（4 级优先级，全部留痕在 attributes.carsales.attribution）：
1. curl_exact           —— transcript 中 agent 的 🔧 execute_shell_command 消息里 curl
                           调用工具网关（±5s 同 tool 名）→ 最硬证据（transcript 原始记录）。
2. segment_skill_anchor —— 未匹配的调用按 ≤120s 间隔聚成段，用段内「唯一 owner 锚定工具」
                           （如 list_sessions 只属于 lead-fusion）确定段主导 agent，
                           段内其余工具若与该 agent 的 skill 依赖有交集则归主导 agent。
3. unique_owner         —— skill_registry 中该工具仅有唯一 owner 的 skill（单 agent 归属）。
4. orchestrator_fallback—— 以上均失败时挂 TeamLeader 编排 span（诚实兜底，不猜测 worker）。

诚实边界（不伪造时间戳）：
- Agent/Skill span 时间范围 = 包住其子 span 实际时间戳 + transcript 消息真实时间戳的区间，
  attributes 标注 derivation: "derived_from_transcript"；
- transcript 覆盖窗口之前的调用（如 family_suv_deal 09:40 预跑段）用段锚定规则推导归属，
  attributes 标注 attribution: "segment_skill_anchor"，绝不冒充 curl 直接证据；
- OTel SDK 语义：span_kind 沿用工具网关风格（agent/skill=internal, tool=client, rag=internal），
  GenAI semconv 属性（gen_ai.agent.name / gen_ai.operation.name / gen_ai.tool.name）与
  otel_exporter.py 保持一致。

依赖：Python 3.11+ 标准库（零第三方依赖；OTel 导出由 otel_exporter.py 可选承担）。

用法:
    python3 tools/agent_span_builder.py                     # 三场景全量构建
    python3 tools/agent_span_builder.py --scenario family_suv_deal
    python3 tools/agent_span_builder.py --check-only        # 只做链路完整性校验
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = PROJECT / "docs" / "RUN_EVIDENCE"
TZ = timezone(timedelta(hours=8))

TRANSCRIPT_FILE = EVIDENCE_DIR / "agentteams_20260816_transcript.json"
FINAL_REPORTS_FILE = EVIDENCE_DIR / "agentteams_20260816_final_reports.json"
SKILL_REGISTRY_FILE = PROJECT / "skills" / "skill_registry.json"
TEAM_SPEC_FILE = PROJECT / "at" / "team_spec.json"

# ---- GenAI semconv 属性常量（与 otel_exporter.py 一致，直接用字符串键）----
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
LLM_SYSTEM = "dashscope"

LEADER_AGENT = "carsales-demo-leader"
CURL_MATCH_TOLERANCE_S = 5      # curl 证据时间容差（transcript 消息秒级毫秒 vs 网关秒级）
SEGMENT_GAP_S = 120             # 连续调用聚段的最大间隔
SKILL_RUN_GAP_S = 600           # 同 skill 连续调用的最大合并间隔（超过则拆为新的 skill 执行段）

SCENARIOS: list[dict[str, str]] = [
    {
        "scenario_id": "family_suv_deal",
        "deal_id": "DEAL-2001",
        "routing_path": "new_deal",
        "trace_file": "trace_family_suv_deal_20260816.json",
        "tree_file": "trace_tree_family_suv_deal_20260816.json",
    },
    {
        "scenario_id": "first_car_finance",
        "deal_id": "DEAL-2002",
        "routing_path": "finance",
        "trace_file": "trace_first_car_finance_20260816.json",
        "tree_file": "trace_tree_first_car_finance_20260816.json",
    },
    {
        "scenario_id": "trade_in_renewal",
        "deal_id": "DEAL-2003",
        "routing_path": "trade_in",
        "trace_file": "trace_trade_in_renewal_20260816.json",
        "tree_file": "trace_tree_trade_in_renewal_20260816.json",
    },
]

# team_spec agent id（下划线风格）↔ Matrix sender / registry owner（连字符风格）
AGENT_ID_TO_MATRIX = {
    "carsales_demo_leader": LEADER_AGENT,
    "lead_intake": "lead-intake",
    "profile_builder": "profile-builder",
    "intent_analyst": "intent-analyst",
    "strategy_planner": "strategy-planner",
    "negotiation_executor": "negotiation-executor",
    "order_executor": "order-executor",
    "customer_ops": "customer-ops",
    "knowledge_miner": "knowledge-miner",
}
WORKER_AGENTS = [v for k, v in AGENT_ID_TO_MATRIX.items() if v != LEADER_AGENT]


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def _parse_gateway_time(s: str) -> datetime:
    """工具网关 time 字段（"2026-08-16T09:40:31+0800"）→ aware datetime。"""
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def _fmt_time(dt: datetime) -> str:
    """aware datetime → 工具网关 time 字段格式（保持证据结构一致）。"""
    return dt.astimezone(TZ).strftime("%Y-%m-%dT%H:%M:%S%z")


def _stable_span_id(trace_id: str, kind: str, name: str, start_iso: str) -> str:
    """确定性 span_id（16 hex）：同一输入重跑结果一致，保证审计证据可复现。"""
    raw = f"{trace_id}|{kind}|{name}|{start_iso}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# transcript 索引：场景窗口 / agent 活动窗口 / curl 工具调用证据
# --------------------------------------------------------------------------
class TranscriptIndex:
    """AgentTeams Matrix transcript 索引（Agent 层信息的唯一事实来源）。"""

    def __init__(self, transcript: list[dict]) -> None:
        self.messages = [
            m for m in transcript
            if m.get("type") == "m.room.message" and m.get("origin_server_ts")
        ]
        self.messages.sort(key=lambda m: m["origin_server_ts"])
        self._scenario_starts = self._find_scenario_starts()
        self._curl_calls = self._extract_curl_calls()

    def _find_scenario_starts(self) -> list[tuple[int, str]]:
        """admin 发出的任务输入消息（含 scenario_id）= 场景起点。"""
        starts: list[tuple[int, str]] = []
        for m in self.messages:
            if not m["sender"].startswith("@admin"):
                continue
            body = m.get("content", {}).get("body", "")
            mo = re.search(r"scenario_id:\s*(\S+)", body)
            if mo:
                starts.append((m["origin_server_ts"], mo.group(1)))
        return starts

    def _extract_curl_calls(self) -> list[dict]:
        """提取 🔧 execute_shell_command 消息里的工具网关 curl 调用（一级归属证据）。"""
        calls: list[dict] = []
        pat = re.compile(r"18089/tools/([^/\"'\\]+)/([a-z_]+\.[a-z_]+)")
        for m in self.messages:
            body = m.get("content", {}).get("body", "")
            if not body.startswith("🔧"):
                continue
            mo = pat.search(body)
            if mo:
                calls.append({
                    "ts": m["origin_server_ts"],
                    "agent": m["sender"].split(":")[0][1:],
                    "url_scenario": mo.group(1),
                    "tool": mo.group(2),
                })
        return calls

    def scenario_window(self, scenario_id: str) -> tuple[int, int]:
        """场景时间窗口 [start_ts, end_ts)（ms）：任务输入 → 下一场景任务输入。"""
        for i, (ts, sid) in enumerate(self._scenario_starts):
            if sid == scenario_id:
                end = (
                    self._scenario_starts[i + 1][0]
                    if i + 1 < len(self._scenario_starts)
                    else self.messages[-1]["origin_server_ts"] + 1
                )
                return ts, end
        raise ValueError(f"transcript 中找不到场景 {scenario_id} 的任务输入")

    def agent_windows(self, start_ts: int, end_ts: int) -> dict[str, dict]:
        """窗口内各 agent 的首/末消息时间与消息数（真实活动证据）。"""
        agg: dict[str, dict] = defaultdict(lambda: {"first": None, "last": None, "messages": 0})
        for m in self.messages:
            if not (start_ts <= m["origin_server_ts"] < end_ts):
                continue
            agent = m["sender"].split(":")[0][1:]
            w = agg[agent]
            w["first"] = m["origin_server_ts"] if w["first"] is None else min(w["first"], m["origin_server_ts"])
            w["last"] = m["origin_server_ts"] if w["last"] is None else max(w["last"], m["origin_server_ts"])
            w["messages"] += 1
        return dict(agg)

    def curls_in_window(self, start_ts: int, end_ts: int) -> list[dict]:
        return [c for c in self._curl_calls if start_ts <= c["ts"] < end_ts]

    def task_input_body(self, scenario_id: str) -> str:
        for ts, sid in self._scenario_starts:
            if sid == scenario_id:
                for m in self.messages:
                    if m["origin_server_ts"] == ts:
                        return m.get("content", {}).get("body", "")
        return ""


# --------------------------------------------------------------------------
# skill registry / team spec 索引
# --------------------------------------------------------------------------
class SkillIndex:
    """skill_registry.json 索引：owner/依赖工具反查。"""

    def __init__(self, registry: dict) -> None:
        self.skills: dict[str, dict] = {s["name"]: s for s in registry.get("skills", [])}
        self.tool_to_skills: dict[str, list[str]] = defaultdict(list)
        for name, s in self.skills.items():
            for tool in s.get("depends_on_tools", []):
                self.tool_to_skills[tool].append(name)

    def owners_of(self, skill_name: str) -> list[str]:
        owner = self.skills[skill_name].get("owner_agent", "")
        if isinstance(owner, list):
            return list(owner)
        if owner == "ALL":
            return []          # 共享 skill：不作为唯一 owner 锚
        return [owner]

    def unique_owner_agent(self, tool: str) -> str | None:
        """该工具在 registry 中是否只指向唯一 owner agent（共享 skill 除外）。"""
        owners: set[str] = set()
        for skill in self.tool_to_skills.get(tool, []):
            owners.update(self.owners_of(skill))
        return next(iter(owners)) if len(owners) == 1 else None

    def skill_for(self, agent: str, tool: str) -> tuple[str | None, bool]:
        """(agent, tool) → (skill, is_shared)。精确 owner 优先，共享 deal-memory 兜底。"""
        exact = [
            sk for sk in self.tool_to_skills.get(tool, [])
            if agent in self.owners_of(sk)
        ]
        if exact:
            return exact[0], False
        shared = [
            sk for sk in self.tool_to_skills.get(tool, [])
            if self.skills[sk].get("owner_agent") == "ALL"
        ]
        if shared:
            return shared[0], True
        return None, False


class TeamSpecIndex:
    """team_spec.json 索引：pipeline 顺序（agent 执行次序）与角色名。"""

    def __init__(self, spec: dict) -> None:
        self.agent_names: dict[str, str] = {}
        for a in spec.get("agents", []):
            matrix_id = AGENT_ID_TO_MATRIX.get(a.get("id", ""), a.get("id", ""))
            self.agent_names[matrix_id] = a.get("name", matrix_id)
        paths = spec.get("workflow", {}).get("routing", {}).get("paths", {})
        self.pipelines: dict[str, list[str]] = {}
        for path, p in paths.items():
            order: list[str] = []
            for step in p.get("pipeline", []):
                agent = AGENT_ID_TO_MATRIX.get(step.get("agent", ""), step.get("agent", ""))
                if agent not in order:
                    order.append(agent)
            self.pipelines[path] = order

    def step_of(self, path: str, agent: str) -> int:
        order = self.pipelines.get(path, [])
        return order.index(agent) + 1 if agent in order else 0


# --------------------------------------------------------------------------
# 工具 span → Agent 归属（4 级规则）
# --------------------------------------------------------------------------
def attribute_tool_spans(
    tool_spans: list[dict],
    transcript: TranscriptIndex,
    skills: SkillIndex,
    window: tuple[int, int],
) -> list[dict]:
    """给每个工具 span 判定执行 agent。返回附上 _agent/_attribution 内部字段的 span 列表。"""
    start_ts, end_ts = window
    curls = transcript.curls_in_window(start_ts, end_ts)
    spans = [dict(s) for s in tool_spans]

    # ---- 第 1 级：curl_exact（transcript 工具调用消息 ±5s 同 tool 最近匹配）----
    for sp in spans:
        sp["_t"] = _parse_gateway_time(sp["time"]).timestamp()
        best: tuple[float, str] | None = None
        for c in curls:
            if c["tool"] != sp["tool"]:
                continue
            dt = abs(c["ts"] / 1000 - sp["_t"])
            if best is None or dt < best[0]:
                best = (dt, c["agent"])
        if best and best[0] <= CURL_MATCH_TOLERANCE_S:
            sp["_agent"], sp["_attribution"] = best[1], "curl_exact"

    # ---- 第 2 级：segment_skill_anchor（≤120s 连续段 + 唯一 owner 锚定）----
    unresolved = sorted(
        (sp for sp in spans if "_agent" not in sp), key=lambda s: s["_t"]
    )
    segment: list[dict] = []
    for sp in unresolved + [None]:  # 哨兵触发收尾
        if sp is not None and (not segment or sp["_t"] - segment[-1]["_t"] <= SEGMENT_GAP_S):
            segment.append(sp)
            continue
        _resolve_segment(segment, skills)
        segment = [sp] if sp is not None else []

    # ---- 第 3 级：unique_owner（registry 唯一归属）----
    for sp in spans:
        if "_agent" not in sp:
            owner = skills.unique_owner_agent(sp["tool"])
            if owner:
                sp["_agent"], sp["_attribution"] = owner, "unique_owner"

    # ---- 第 4 级：orchestrator_fallback（TeamLeader 兜底，诚实标注）----
    for sp in spans:
        if "_agent" not in sp:
            sp["_agent"], sp["_attribution"] = LEADER_AGENT, "orchestrator_fallback"
    return spans


def _resolve_segment(segment: list[dict], skills: SkillIndex) -> None:
    """段内归属：唯一 owner 锚定工具确定锚点，其余工具归「时间上最近的锚」agent。

    锚点定义：registry 中该工具的全部 owner 候选收敛到唯一 agent（如 list_sessions
    → lead-fusion → lead-intake）。未归属工具按与锚点的时间距离从近到远依次尝试，
    与锚 agent 的 skill 依赖有交集即归属（交集校验防止跨 skill 错挂，无交集则
    尝试次近锚，全部失败留到第 3/4 级规则）。
    """
    if not segment:
        return
    anchors: list[tuple[float, str]] = []  # (时间戳, agent)
    for sp in segment:
        owner = skills.unique_owner_agent(sp["tool"])
        if owner and owner != LEADER_AGENT:
            sp["_agent"], sp["_attribution"] = owner, "segment_skill_anchor"
            anchors.append((sp["_t"], owner))
    if not anchors:
        return
    for sp in segment:
        if "_agent" in sp:
            continue
        for _ts, anchor_agent in sorted(anchors, key=lambda a: abs(a[0] - sp["_t"])):
            skill, _shared = skills.skill_for(anchor_agent, sp["tool"])
            if skill:
                sp["_agent"], sp["_attribution"] = anchor_agent, "segment_skill_anchor"
                break


# --------------------------------------------------------------------------
# 三层 span 构建
# --------------------------------------------------------------------------
def build_skill_spans(
    agent: str,
    agent_children: list[dict],
    skills: SkillIndex,
    trace_id: str,
) -> tuple[list[dict], list[dict]]:
    """把某 agent 名下的工具 span 按时序切成「连续同 skill 段」，生成 skill span。

    返回 (skill_spans, 直接挂 agent 的工具 span)。无 skill 匹配的工具直挂 agent 层
    （诚实：不为凑三层而虚构 skill 归属）。
    """
    ordered = sorted(agent_children, key=lambda s: s["_t"])
    skill_spans: list[dict] = []
    direct: list[dict] = []
    run_skill: str | None = None
    run_last_t: float = 0.0
    run_items: list[dict] = []
    seq_counter: Counter = Counter()

    def _flush() -> None:
        nonlocal run_skill, run_items
        if run_skill is None or not run_items:
            run_skill, run_items = None, []
            return
        meta = skills.skills[run_skill]
        seq_counter[run_skill] += 1
        start = min(_parse_gateway_time(it["time"]) for it in run_items)
        last = max(
            _parse_gateway_time(it["time"]) + timedelta(milliseconds=it.get("duration_ms", 0))
            for it in run_items
        )
        name = f"{agent}.{run_skill}#{seq_counter[run_skill]}"
        span_id = _stable_span_id(trace_id, "skill", name, _fmt_time(start))
        attributions = Counter(it["_attribution"] for it in run_items)
        span = {
            "time": _fmt_time(start),
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": None,  # 稍后回填 agent span_id
            "span_kind": "skill",
            "status": "ok" if all(it.get("status") == "ok" for it in run_items) else "error",
            "attributes": {
                GEN_AI_SYSTEM: LLM_SYSTEM,
                GEN_AI_OPERATION_NAME: "invoke_skill",
                "carsales.skill.name": run_skill,
                "carsales.skill.version": meta.get("version", ""),
                "carsales.skill.type": meta.get("type", ""),
                "carsales.skill.risk_level": meta.get("risk_level", ""),
                "carsales.skill.mcp_mapping": meta.get("mcp_mapping", ""),
                "carsales.skill.idempotent": bool(meta.get("idempotent", False)),
                "carsales.skill.tool_calls": len(run_items),
                "carsales.skill.owner_agent": agent,
                "carsales.skill.attribution": dict(attributions),
                "derivation": "derived_from_transcript",
            },
            "duration_ms": round((last - start).total_seconds() * 1000, 2),
            "name": name,
        }
        for it in run_items:
            it["_parent_skill"] = span_id
        skill_spans.append(span)
        run_skill, run_items = None, []

    for sp in ordered:
        skill, shared = skills.skill_for(agent, sp["tool"])
        if skill is None:
            direct.append(sp)
            continue
        # 同 skill 且距上次调用 ≤ SKILL_RUN_GAP_S 才合并进同一执行段（否则新起 #seq）
        if skill != run_skill or sp["_t"] - run_last_t > SKILL_RUN_GAP_S:
            _flush()
            run_skill = skill
        sp["_skill_shared"] = shared
        run_items.append(sp)
        run_last_t = sp["_t"]
    _flush()
    return skill_spans, direct


def build_agent_span(
    agent: str,
    children: list[dict],
    window_info: dict | None,
    step: int,
    role: str,
    output: str,
    trace_id: str,
) -> dict:
    """构建 worker agent span：时间范围包住子 span + transcript 真实消息时间。"""
    child_starts = [_parse_gateway_time(sp["time"]) for sp in children]
    child_ends = [
        _parse_gateway_time(sp["time"]) + timedelta(milliseconds=sp.get("duration_ms", 0))
        for sp in children
    ]
    msg_first = datetime.fromtimestamp(window_info["first"] / 1000, TZ) if window_info else None
    msg_last = datetime.fromtimestamp(window_info["last"] / 1000, TZ) if window_info else None
    candidates = child_starts + ([msg_first] if msg_first else [])
    start = min(candidates)
    end = max(child_ends + ([msg_last] if msg_last else []))
    window_expanded = bool(
        msg_first and child_starts and min(child_starts) < msg_first
    ) or not window_info
    name = f"{agent}.task_execution"
    attrs = {
        GEN_AI_SYSTEM: LLM_SYSTEM,
        GEN_AI_AGENT_NAME: agent,
        GEN_AI_OPERATION_NAME: "execute_task",
        "carsales.agent.role": role,
        "carsales.agent.pipeline_step": step,
        "carsales.agent.output_summary": output,
        "derivation": "derived_from_transcript",
    }
    if window_info:
        attrs["carsales.agent.transcript_messages"] = window_info["messages"]
        attrs["carsales.agent.first_message_time"] = _fmt_time(msg_first)
        attrs["carsales.agent.last_message_time"] = _fmt_time(msg_last)
    if window_expanded:
        attrs["carsales.agent.window_expanded_to_cover_child_spans"] = True
    return {
        "time": _fmt_time(start),
        "trace_id": trace_id,
        "span_id": _stable_span_id(trace_id, "agent", name, _fmt_time(start)),
        "parent_span_id": None,  # 稍后回填 leader span_id
        "span_kind": "agent",
        "status": "ok" if all(sp.get("status") == "ok" for sp in children) else "error",
        "attributes": attrs,
        "duration_ms": round((end - start).total_seconds() * 1000, 2),
        "name": name,
    }


def parse_final_report_outputs(reports: dict, deal_id: str) -> dict[str, str]:
    """从本场景 final report markdown 表格提取各 agent 关键产出（agent → output 文本）。"""
    outputs: dict[str, str] = {}
    rec = reports.get(deal_id)
    if rec:
        for line in rec.get("report", "").splitlines():
            mo = re.match(r"\|\s*\d+\s*\|[^|]+\|([^|]+)\|[^|]+\|([^|]*)\|", line)
            if not mo:
                continue
            agent = mo.group(1).strip()
            output = mo.group(2).strip()
            if agent in WORKER_AGENTS and output:
                outputs[agent] = output
    return outputs


def build_scenario_tree(scen: dict[str, str], transcript: TranscriptIndex,
                        skills: SkillIndex, spec: TeamSpecIndex) -> dict:
    """构建单场景三层 trace 树（leader root → agent → skill → tool）。"""
    trace_data = _load_json(EVIDENCE_DIR / scen["trace_file"])
    tool_spans_raw = trace_data.get("result", []) if isinstance(trace_data, dict) else trace_data
    trace_id = tool_spans_raw[0]["trace_id"]
    window = transcript.scenario_window(scen["scenario_id"])
    windows = transcript.agent_windows(*window)

    # 1) 工具 span 归属 agent（4 级规则）
    spans = attribute_tool_spans(tool_spans_raw, transcript, skills, window)
    attribution_stats = Counter(sp["_attribution"] for sp in spans)

    # 2) 按 agent 分组 → 切 skill 段
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for sp in spans:
        by_agent[sp["_agent"]].append(sp)

    outputs = parse_final_report_outputs(
        _load_json(FINAL_REPORTS_FILE), scen["deal_id"]
    ) if FINAL_REPORTS_FILE.exists() else {}

    all_spans: list[dict] = []
    agent_spans: dict[str, dict] = {}
    for agent in WORKER_AGENTS:
        children = by_agent.get(agent, [])
        if not children and agent not in windows:
            continue  # 该场景未参与（如 finance 路径无 lead-intake 时不造 span）
        skill_spans, direct = build_skill_spans(agent, children, skills, trace_id)
        agent_span = build_agent_span(
            agent, children, windows.get(agent),
            spec.step_of(scen["routing_path"], agent),
            spec.agent_names.get(agent, agent), outputs.get(agent, ""), trace_id,
        )
        agent_spans[agent] = agent_span
        all_spans.extend(skill_spans + [agent_span])
        for sp in direct:
            sp["_parent_agent"] = agent_span["span_id"]
        for sk in skill_spans:
            sk["_parent_agent"] = agent_span["span_id"]

    # 3) TeamLeader 编排 root span（覆盖任务输入 → 最终报告的真实时间）
    leader_window = windows.get(LEADER_AGENT)
    child_bounds: list[datetime] = []
    for sp in spans:
        child_bounds.append(_parse_gateway_time(sp["time"]))
        child_bounds.append(
            _parse_gateway_time(sp["time"]) + timedelta(milliseconds=sp.get("duration_ms", 0))
        )
    leader_start = datetime.fromtimestamp(window[0] / 1000, TZ)
    leader_end = datetime.fromtimestamp(
        (leader_window["last"] if leader_window else window[1] - 1) / 1000, TZ
    )
    start = min([leader_start] + child_bounds)
    end = max([leader_end] + child_bounds)
    leader_span = {
        "time": _fmt_time(start),
        "trace_id": trace_id,
        "span_id": _stable_span_id(trace_id, "agent", "TeamLeader.orchestration", _fmt_time(start)),
        "parent_span_id": None,
        "span_kind": "agent",
        "status": "ok",
        "attributes": {
            GEN_AI_SYSTEM: LLM_SYSTEM,
            GEN_AI_AGENT_NAME: LEADER_AGENT,
            GEN_AI_OPERATION_NAME: "orchestrate_deal",
            "carsales.agent.role": "TeamLeader (AgentTeams 编排)",
            "carsales.deal_id": scen["deal_id"],
            "carsales.scenario_id": scen["scenario_id"],
            "carsales.routing_path": scen["routing_path"],
            "carsales.execution_mode": "DAG (8 nodes, AgentTeams v1.1.2 + Matrix)",
            "carsales.agent.transcript_messages": leader_window["messages"] if leader_window else 0,
            "derivation": "derived_from_transcript",
        },
        "duration_ms": round((end - start).total_seconds() * 1000, 2),
        "name": "TeamLeader.orchestration",
    }
    all_spans.append(leader_span)

    # leader 名下的工具 span（fallback 或 leader 直接调用）直挂编排 span
    for sp in spans:
        if sp["_agent"] == LEADER_AGENT:
            sp["_parent_agent"] = leader_span["span_id"]

    # 4) 工具 span 定稿：回填 parent + 归属 attributes（其余字段原样保留审计源真相）
    final_tool_spans: list[dict] = []
    for sp in spans:
        skill_sid = sp.get("_parent_skill")
        agent_sid = sp.get("_parent_agent") or agent_spans[sp["_agent"]]["span_id"]
        out = {k: v for k, v in sp.items() if not k.startswith("_")}
        out["parent_span_id"] = skill_sid or agent_sid
        out.setdefault("attributes", {})
        out["attributes"][GEN_AI_SYSTEM] = LLM_SYSTEM
        out["attributes"][GEN_AI_TOOL_NAME] = sp["tool"]
        out["attributes"]["carsales.agent.name"] = sp["_agent"]
        out["attributes"]["carsales.attribution"] = sp["_attribution"]
        if sp.get("_parent_skill"):
            out["attributes"]["carsales.skill.name"] = next(
                sk["attributes"]["carsales.skill.name"]
                for sk in all_spans if sk["span_kind"] == "skill" and sk["span_id"] == sp["_parent_skill"]
            )
        final_tool_spans.append(out)

    # 5) skill/agent span 回填 parent + 排序输出（父先于子，保证 OTel 重放链接正确）
    for sp in all_spans:
        if sp["span_kind"] == "skill":
            sp["parent_span_id"] = sp.pop("_parent_agent")
        elif sp["span_kind"] == "agent" and sp is not leader_span:
            sp["parent_span_id"] = leader_span["span_id"]
    # 显式深度排序：同时间戳时保证 root → agent → skill → tool 层级顺序
    # （leader 与首 worker agent 常同秒起跑，仅靠 kind 权重无法区分 root 与 worker）
    _depth = {leader_span["span_id"]: 0}
    for sp in all_spans:
        if sp is leader_span:
            continue  # leader 是 root（depth 0），不会被下面按 kind 的规则覆盖
        if sp["span_kind"] == "agent":
            _depth[sp["span_id"]] = 1
        elif sp["span_kind"] == "skill":
            _depth[sp["span_id"]] = 2
    for sp in final_tool_spans:
        _depth[sp["span_id"]] = 3 if sp.get("parent_span_id") in {
            s["span_id"] for s in all_spans if s["span_kind"] == "skill"
        } else 2
    all_spans = sorted(
        all_spans + final_tool_spans,
        key=lambda s: (_parse_gateway_time(s["time"]), _depth[s["span_id"]]),
    )

    # 6) 层级统计 + 链路完整性
    layer_counts = Counter(s["span_kind"] for s in all_spans)
    non_root = [s for s in all_spans if s is not leader_span]
    parented = [s for s in non_root if s["parent_span_id"]]
    tool_like = [s for s in all_spans if s["span_kind"] in ("tool", "rag")]
    tool_parented = [s for s in tool_like if s["parent_span_id"]]
    id_set = {s["span_id"] for s in all_spans}
    dangling = [s["span_id"] for s in all_spans
                if s["parent_span_id"] and s["parent_span_id"] not in id_set]

    evidence = {
        "ok": len(dangling) == 0,
        "generated_by": "tools/agent_span_builder.py",
        "scenario_id": scen["scenario_id"],
        "deal_id": scen["deal_id"],
        "trace_id": trace_id,
        "sources": {
            "transcript": "docs/RUN_EVIDENCE/agentteams_20260816_transcript.json",
            "tool_trace": f"docs/RUN_EVIDENCE/{scen['trace_file']}",
            "skill_registry": "skills/skill_registry.json",
            "team_spec": "at/team_spec.json",
            "final_reports": "docs/RUN_EVIDENCE/agentteams_20260816_final_reports.json",
        },
        "span_layers": {
            "agent_spans": layer_counts["agent"],
            "skill_spans": layer_counts["skill"],
            "tool_spans": layer_counts["tool"],
            "rag_spans": layer_counts["rag"],
            "total": len(all_spans),
        },
        "link_integrity": {
            "spans_with_parent": len(parented),
            "spans_expected_parent": len(non_root),
            "all_span_parent_rate": round(len(parented) / len(non_root), 4) if non_root else 1.0,
            "tool_spans_with_parent": len(tool_parented),
            "tool_spans_total": len(tool_like),
            "tool_span_parented_rate": round(len(tool_parented) / len(tool_like), 4) if tool_like else 1.0,
            "dangling_parent_refs": dangling,
        },
        "attribution_methods": dict(attribution_stats),
        "honest_boundary": (
            "Agent/Skill 层 span 由 AgentTeams Matrix transcript 推导（derivation=derived_from_transcript），"
            "时间范围包住子 span 实际时间戳与 transcript 真实消息时间；工具层 span 为网关审计源真相原样保留，"
            "仅回填 parent_span_id。transcript 窗口之外的调用（预跑段）按段锚定规则推导归属并标注 "
            "attribution=segment_skill_anchor，不冒充直接证据。"
        ),
        "result": all_spans,
    }
    return evidence


def verify_link_integrity(evidence: dict) -> list[str]:
    """链路完整性校验：parent 引用存在 + 父 span 时间范围包住子 span。"""
    errors: list[str] = []
    spans = evidence["result"]
    by_id = {s["span_id"]: s for s in spans}
    roots = [s for s in spans if not s["parent_span_id"]]
    if len(roots) != 1:
        errors.append(f"根 span 数量 = {len(roots)}（应为 1）")
    for s in spans:
        pid = s["parent_span_id"]
        if pid and pid not in by_id:
            errors.append(f"{s['name']}: parent_span_id {pid} 不存在")
            continue
        if pid:
            parent = by_id[pid]
            c_start = _parse_gateway_time(s["time"])
            c_end = c_start + timedelta(milliseconds=s.get("duration_ms", 0))
            p_start = _parse_gateway_time(parent["time"])
            p_end = p_start + timedelta(milliseconds=parent.get("duration_ms", 0))
            if c_start < p_start or c_end > p_end:
                errors.append(
                    f"{s['name']} ({c_start:%H:%M:%S}~{c_end:%H:%M:%S}) "
                    f"超出父 {parent['name']} ({p_start:%H:%M:%S}~{p_end:%H:%M:%S}) 范围"
                )
    return errors


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="构建 Agent→Skill→Tool 三层全链路 trace 树")
    ap.add_argument("--scenario", choices=[s["scenario_id"] for s in SCENARIOS],
                    help="只构建指定场景（默认三场景全量）")
    ap.add_argument("--check-only", action="store_true", help="只校验已有 trace_tree 文件，不重新生成")
    args = ap.parse_args()

    print("Agent→Skill→Tool 三层全链路 Trace 构建（可观测补全，任务 #2）")
    print("=" * 70)
    print(f"transcript: {TRANSCRIPT_FILE.relative_to(PROJECT)}")
    print(f"归属规则: curl_exact(±{CURL_MATCH_TOLERANCE_S}s) → segment_skill_anchor"
          f"(≤{SEGMENT_GAP_S}s) → unique_owner → orchestrator_fallback")
    print()

    targets = [s for s in SCENARIOS if not args.scenario or s["scenario_id"] == args.scenario]

    if args.check_only:
        ok_all = True
        for scen in targets:
            path = EVIDENCE_DIR / scen["tree_file"]
            if not path.exists():
                print(f"[{scen['scenario_id']}] ✗ 缺少 {scen['tree_file']}")
                ok_all = False
                continue
            evidence = _load_json(path)
            errors = verify_link_integrity(evidence)
            li = evidence["link_integrity"]
            status = "✓" if not errors and li["dangling_parent_refs"] == [] else "✗"
            print(f"[{scen['scenario_id']}] {status} tool 挂载率="
                  f"{li['tool_span_parented_rate']:.1%}，全 span 挂载率={li['all_span_parent_rate']:.1%}")
            for e in errors:
                print(f"    {e}")
            ok_all = ok_all and not errors
        sys.exit(0 if ok_all else 1)

    transcript = TranscriptIndex(_load_json(TRANSCRIPT_FILE))
    skills = SkillIndex(_load_json(SKILL_REGISTRY_FILE))
    spec = TeamSpecIndex(_load_json(TEAM_SPEC_FILE))

    for scen in targets:
        evidence = build_scenario_tree(scen, transcript, skills, spec)
        errors = verify_link_integrity(evidence)
        out_path = EVIDENCE_DIR / scen["tree_file"]
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

        sl, li = evidence["span_layers"], evidence["link_integrity"]
        print(f"[{scen['scenario_id']}] trace_id={evidence['trace_id'][:16]}...")
        print(f"  层级: {sl['agent_spans']} agent / {sl['skill_spans']} skill / "
              f"{sl['tool_spans']} tool / {sl['rag_spans']} rag（共 {sl['total']} span）")
        print(f"  链路: 工具 span 挂载率 {li['tool_spans_with_parent']}/{li['tool_spans_total']}"
              f" = {li['tool_span_parented_rate']:.1%}；全 span 挂载率 "
              f"{li['spans_with_parent']}/{li['spans_expected_parent']} = {li['all_span_parent_rate']:.1%}")
        print(f"  归属: {evidence['attribution_methods']}")
        print(f"  校验: {'✓ 通过' if not errors else '✗ ' + '; '.join(errors[:3])}")
        print(f"  落盘: {out_path.relative_to(PROJECT)}")
        print()
    print("===== AGENT SPAN BUILDER: ALL DONE =====")


if __name__ == "__main__":
    main()
