# SalesFlow 架构总览

> 面向评审：本文件用一张分层架构图统合 SalesFlow 的全部能力（AgentTeams 编排 → 8 Worker → Skill → MCP/工具 → RAG/记忆 → 可观测/审计），并标注 P2 各成果落点，说明设计理念、必要性、可替换性与端到端闭环。

## 1. 分层架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AgentTeams 协同层（at/）                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  TeamLeader: carsales-demo-leader                                 │  │
│  │  职责：接收任务 → 提取 deal_type → 路由 → 派发 → 审批门禁 → 报告  │  │
│  │  映射：team_spec.json agents[]+team_leader / workflow.routing      │  │
│  └──────┬──────────────────────────────────────────────────────┬─────┘  │
│         │ 主链串行派发（G1 调度）                                │ async  │
│         ▼                                                      ▼ fanout │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    ┌──────────┐    │
│  │Lead Intake│→│Profile   │→│Intent    │→│Strategy  │…   │Customer  │    │
│  │          │ │Builder   │ │Analyst   │ │Planner   │    │Ops       │    │
│  ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤    ├──────────┤    │
│  │Negotiation│→│Order     │                  │Knowledge │    │
│  │Executor  │ │Executor  │                  │Miner     │    │
│  └──────────┘ └──────────┘                  └──────────┘    │
│   8 业务 Worker，各按 Output Contract 产出（G2）                │        │
└─────────┬──────────────────────────────────────────────────────┘        │
          │ W3C traceparent(00-<trace_id>-<agent_span_id>-01) 传播        │
          ▼                                                               │
┌─────────────────────────────────────────────────────────────────────────┐
│  Skill 能力抽象层（skills/ 13 = 11 自定义 + 2 官方用云）              │
│  lead-fusion | profile-building | intent-scoring | car-recommendation   │
│  quote-pricing | negotiation-guard | test-drive-booking | finance-plan  │
│  order-safe-execute | deal-memory | case-mining | evidence-archive       │
│  sms-approval-alert（官方短信，与 evidence-archive 同为官方用云 Skill） │
│  Skill 封装"做什么"，不绑定"怎么做"——可被多 Agent / 多场景复用          │
└─────────┬───────────────────────────────────────────────────────────────┘
          │                                                              │
          ▼                                                              │
┌─────────────────────────────────────────────────────────────────────────┐
│  工具连接层（tools/，25 函数，HTTP 网关 + MCP Server 等价）              │
│  ┌──────────────────┐         ┌──────────────────────────────┐         │
│  │ HTTP mock 网关    │ ◄──────►│ FastMCP stdio Server (25 工具)│         │
│  │ mock_tool_server  │  等价   │ mcp_server.py                 │         │
│  │ /tools/{sid}/{fn} │  仅协议 │ _STATE_CACHE 保跨调用状态      │         │
│  │ +FAULT_INJECTION  │  适配   └──────────────────────────────┘         │
│  └────────┬─────────┘                                                    │
│           │ 业务逻辑复用 LocalMockTools（零重构）                        │
│  CRM | Inventory | Price | TradeIn | Finance | TestDrive | Order        │
│  | Knowledge | WeChat | SMS | Verify（11 域 25 函数）                  │
│  + approve/reject/confirm_order/audit_trail（P2.3 安全审计原语）        │
│  + mock_tradein.assess_vehicle/request_uplift（DEAL-2004 置换评估）    │
│  + mock_sms.send_approval_alert（官方短信 Skill，L2 审批触达）          │
└─────────┬───────────────────────────────────────────────────────────────┘
          │                                                              │
          ▼                                                              │
┌─────────────────────────────────────────────────────────────────────────┐
│  数据与上下文层                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
│  │ RAG 三后端可插拔 │  │ Agent 记忆存储    │  │ scenarios/*.json │      │
│  │ vector_rag.py    │  │ JSONL + 语义召回  │  │ 4 场景脱敏数据   │      │
│  │ tfidf/embedding/ │  │ 跨 deal 经验沉淀 │  │ → 真实 CRM/DMS   │      │
│  │ pgvector(PoC)    │  │ → PolarDB 长记忆 │  │                  │      │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘      │
└─────────┬───────────────────────────────────────────────────────────────┘
          │                                                              │
          ▼                                                              │
┌─────────────────────────────────────────────────────────────────────────┐
│  可观测与审计层（OTel GenAI 语义）                                       │
│  Trace(span: agent/skill/tool/rag) + Log(决策/审批/失败) + Metrics     │
│  + 三层trace树(agent_span_builder, root=TeamLeader, 挂载率100%)       │
│  + audit_trail(actions, append-only JSONL, trace_id 关联)               │
│  + OSS 证据归档(evidence-archive Skill, key 含 trace_id)               │
│  + 故障注入验证(fault_injection_test, 7用例52断言, 降级可观测)        │
│  → LoongSuite / AgentScope Studio / AgentLoop 全链路采集（复赛）        │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. AgentTeams 协同设计基点映射

| 框架能力 | SalesFlow 落地 | 证据 |
| --- | --- | --- |
| 角色编排 | `team_spec.json` agents[] + team_leader；8 Worker + 1 TeamLeader | `at/team_spec.json` |
| 任务拆解 | `workflow.routing.paths[deal_type].pipeline`；new_deal/finance/trade_in 三路径 | `at/team_spec.json` |
| 上下文传递 | 上游 Worker output → 下游 input（MinIO 共享存储 meta.json/plan.md/result.md + Matrix DM room + `{{quote_id}}`/`{{slot}}`/`{{plan_id}}` 占位符运行时解析） | `agentteams_real_run_transcript.json`（DM room 消息流）、`DEAL-*_output.json`（Worker 输出契约） |
| 协同执行 | 主链串行 + `async_after_close`（customer_ops/knowledge_miner）异步扇出；Worker 通过 HTTP 工具网关主动调用工具完成任务 | AgentTeams 真框架运行（11 容器 v1.1.2 + Matrix 协议，2026-08-16 三场景全闭环） |
| 状态追踪 | 每 Worker agent span + 其下 tool span，统一 trace_id 串成 trace 树；工具网关 OTel-GenAI 风格 span（两轮真跑 79 + 116 次调用，成功率 100%）；离线由 `agent_span_builder.py` 构建 Agent→Skill→Tool 三层树（TeamLeader root，工具挂载率 100%） | `RUN_EVIDENCE/DEAL-*_trace.json`、`RUN_EVIDENCE/trace_*_20260816.json`（真实 AgentTeams 运行工具调用 Trace）、`RUN_EVIDENCE/trace_tree_*_20260816.json`（三层树） |
| 人机协同 | 审批门禁：approve/reject/confirm/rollback，高风险动作禁止默认放行 | `approval_gate` 阶段（**LLM 自主推理决策**，`decision_source` 诚实标注） |

## 3. 安全审计闭环（P2.3 审计原语 + 3 个 LLM 自主决策点）

```
Worker 管线产出            TeamLeader 审批门禁（百炼 LLM 自主推理）     执行层              审计层
─────────────────       ──────────────────────────────────────      ──────────────    ──────────────
apply_discount(超授权) ─┐                                          ┌─ approve ─→ confirm_order ─┐
submit_approval(征信) ─┤  忠实上下文 ─→ LLM 自主推理 approve/reject/pending │                      ├─ audit_trail
create_order(草稿)   ─┘  (金额/授权底线/客户/召回，不操纵决策方向)  ├─ reject ─→ rollback_order ─┤  (append-only
                          │  无 key/失败 → 降级 fallback_config      │                      │  JSONL,
                          └─ pending ─→ human_handoff(禁止默认放行) └─ check_deal ──────────┘  trace_id 关联)
                                                                  ↓
                                                          rolled_back / won / pending_approval
```

### 三个 LLM 自主决策点（`llm_client.py`，百炼 qwen-plus，env 可切 qwen-max）

| 决策点 | 位置 | LLM 自主决定 | 诚实分化证据 | 降级 |
| --- | --- | --- | --- | --- |
| 1. 审批门禁 | approval_gate | approve/reject/pending | DEAL-2001 reject→rollback / DEAL-2002 approve→confirm / DEAL-2003 pending→human_handoff | fallback_config |
| 2. 车型推荐审查 | strategy_review | fit_confidence + risk_flag | DEAL-2002 fit=medium risk=preference_mismatch（如实标 mismatch） | fallback_config |
| 3. 工具调用顺序 | strategy_planner tool_planning | 4 工具调用先后顺序 | DEAL-2003 LLM 把 get_policy 提前到 check_stock 之前（意向模糊→先取价格政策） | fallback_config |

**诚实边界**：`decision_source` 字段全程标注 `llm`/`fallback_config`，不伪装；prompt 只给忠实业务上下文，不操纵决策方向；`raw_response` 留痕可回放审计。

- **LLM 自主决策（三个决策点）**：①审批门禁由百炼 LLM（qwen-plus，可切 qwen-max）基于忠实业务上下文自主推理 approve/reject/pending；②strategy_planner 车型推荐由 LLM 自主评估匹配度 + 风险标记（DEAL-2002 诚实标 preference_mismatch，非一律 high）；③strategy_planner 工具调用顺序由 LLM 自主规划（DEAL-2003 LLM 把 get_policy 提前到 check_stock 之前，体现场景化编排）。`decision_source` 诚实标注 `llm`/`fallback_config`，无 key 仍 ALL PASS；`*_llm_decision.json` + `*_llm_recommendation.json` + `*_tool_plan.json` 证据含完整上下文 + 原始返回，可回放审计。
- **决策与执行分离**：`reject` 只标记 `rollback_requested`，由执行层显式 `rollback_order`。
- **门禁**：`confirm_order` 校验关联审批必须 approved 且无 rejected。
- **三安全分支**：DEAL-2001 reject→rollback（rolled_back）、DEAL-2002 approve→confirm（won）、DEAL-2003 pending→human_handoff。
- **审计轨迹**：6/4/4 条 action，全量 `trace_id` 关联，append-only 落盘，可按 approval_id/order_id 筛选。

## 4. 可观测性：OTel 真落地 + 官方用云 Skill 真集成（P3.3 + P3.2）

| 能力 | 实现 | 迁移方向 |
| --- | --- | --- |
| 三层 trace 树构建 | `agent_span_builder.py`：从 transcript + skill_registry + 网关 trace 推导 **Agent→Skill→Tool 三层 span**（TeamLeader 为 root；182 span = 27 agent + 39 skill + 99 tool + 17 rag，工具 span 挂载率 100%，12/116 二级推导显式标注） | LoongSuite/AgentScope Studio 运行时原生采集（复赛） |
| OTel 重放导出 | `otel_exporter.py`：opentelemetry-sdk 1.27.0 TracerProvider + ConsoleSpanExporter + FileSpanExporter，工具网关 hand-written span + 三层 trace 树重放为真 OTel Span（261 span / 6 trace，GenAI semconv） | OTLP Collector → LoongSuite/AgentScope Studio |
| OSS 真调用 | `evidence_archive.py`：OssObjectStore 真阿里云 OSS REST（OSS v1 HMAC-SHA1 签名，零 oss2 依赖），有凭证真调/无凭证降级本地，`store_type` 标注；签名已验证 + MinIO PUT/GET 往返成功 | MCP Server（oss_put/get/list tool） |
| 短信真调用 | `sms_alert.py`：AliyunSmsSender 真阿里云 Dysmsapi REST（RPC V1 HMAC-SHA1 签名，零 SDK 依赖），有凭证真调/无凭证降级本地外呼记录，`channel_type` 标注；签名模板控制台报备为生产前置 | MCP Server（sms.approval.alert tool） |
| 百炼模型服务 | `llm_client.py`：百炼 OpenAI 兼容 endpoint 真调用（**三个 LLM 决策点** + LLM-as-Judge），`response_format: json_object` | Higress AI 网关统一路由 |

- **诚实边界**：OTel 重放导出 261 span（6 trace = 3 工具层 + 3 三层树，事后导出）为可观测证据；三层树中 Agent/Skill 层 span 由 transcript 推导（`derivation=derived_from_transcript`，其中 12/116 条工具调用为 segment_skill_anchor 二级推导显式标注）；OSS `store_type` 区分 `oss_rest`/`local`；短信 `channel_type` 区分 `aliyun_sms_rest`/`local_mock`；LLM `decision_source` 区分 `llm`/`fallback_config`。运行时原生 Agent/Skill span 采集由 AgentTeams 运行时或 LoongSuite/AgentScope Studio 承接（复赛接入）。

## 5. RAG 与上下文增强（P2.2，4 项实现 4 项）

| 能力 | 实现 | 迁移方向 |
| --- | --- | --- |
| Agent 记忆存储 | `tools/mock_tools.py` 内置 JSONL 持久化 + 时间窗口查询 + TF-IDF 语义召回（`recall_semantic` 接口） | PolarDB 长记忆 |
| 知识库 RAG | 三后端可插拔（`tools/vector_rag.py`）：`local_tfidf`（TF-IDF 基线）/ `local_embedding`（稠密向量，即线上 mock_tools 后端）/ `pgvector`（真 SQL 适配层 PoC：upsert/ANN 查询/时间窗口函数，DDL 见 `tools/pgvector_migration/DDL.sql`）；统一 `search()` 接口，结果结构与 evidence_refs 三后端一致 | PolarDB pgvector（迁移 PoC 已实证：14 查询等价性验证 8/8 回归守护 + 9/9 空结果修复 + 双非空 Top-3 overlap 1.0，见 [RAG_PGVECTOR_MIGRATION.md](RAG_PGVECTOR_MIGRATION.md)） |
| 共享状态管理 | `vars` 字典 + `{{var}}` 占位符运行时解析（多 Worker 并发安全的上下文传递） | — |
| 轨迹可观测 | trace + logs + audit_trail 持久化（JSONL + OSS 归档）；故障注入验证非 happy path 可观测（7 用例 52 断言：降级 span/audit/log 三处留痕） | LoongSuite/AgentScope Studio |

## 5. 可观测体系（OTel GenAI 语义）

| 数据类型 | 覆盖 | 语义规范 | 采集与存储 |
| --- | --- | --- | --- |
| Trace | agent/skill/tool/rag 四类 span（三层树：Agent→Skill→Tool，TeamLeader root） | trace_id/span_id/parent_span_id/span_kind/status/duration_ms/attributes | 网关 JSONL + 真实 AgentTeams 运行 Trace + 三层树（`trace_tree_*_20260816.json`） |
| Log | 决策依据/审批事件/失败原因/审批决策 | event/level/attributes + trace_id 关联 | `tools.logs` + append-only JSONL |
| Metrics | 调用数/成功率/时延/按工具按类型 | tool_calls/tool_success/by_tool/by_kind | `tools.metrics` + `/metrics` 端点 |
| Audit | 高风险动作结构化轨迹 | action_id/name/risk_level/time + 关联业务键 | append-only `_audit.jsonl` + `/audit` 端点 |

W3C `traceparent` 同时传播 `trace_id` + `parent_span_id`，工具 span 挂到发起它的 Agent span 之下，形成 Agent→Skill→Tool 完整 trace 树。离线侧，`tools/agent_span_builder.py` 从 transcript + skill_registry 推导补全三层树（182 span，工具 span 挂载率 100%，TeamLeader 为 root），可被 `otel_exporter.py` 重放为真 OTel SDK Span（261 span）。

## 6. 评估闭环

- **离线自检 87/87**（4 场景 + 审计闭环 = 56 + DEAL-2004 复合场景 31；验证时口径 56，见 EVIDENCE.md E1/E34）。
- **Golden 13/13 + Badcase 7/7 = 1.0**（16 维度全 1.0），新增 G13 审批闭环（approve→confirm→won）、B07 驳回→门禁→回滚→审计。
- **Agent 决策层评估**（`tools/agent_eval.py`）：从 transcript 按 (场景, Agent 环节) 提取实际工具序列 vs 场景 Golden（命中率 1.0/1.0/0.9167，平均 0.9722）+ 跨环节顺序约束 12/12 + RAG 覆盖 1.0×3；评估结果追加写入 `eval_report.json` 的 `agent_layer_eval` 维度（原内容保留）；第四场景 DEAL-2004 以 Golden 期望序列离线重放验证（17/17 命中 + 6/6 复合顺序约束，`offline_expected_replay` 诚实标注，不与真实运行指标混算）。
- **故障注入韧性验证**（`tools/fault_injection_test.py`）：4 故障类型 × 7 用例 52 断言全过，非 happy path 降级/重试/隔离/恢复证据（见 EVIDENCE.md E33）。
- **LLM-as-Judge** 三场景对齐：DEAL-2001（E15）+ DEAL-2002/2003（真实百炼调用，`judge_source=llm`）；无 API Key 时离线规则评估降级。
- **结果回流 Dataset**：失败用例与评判结果用于专家调优 Prompt/Skill/RAG/风控阈值。

## 7. 可替换性与迁移成本

| 当前实现 | 后续替换 | 迁移成本 |
| --- | --- | --- |
| HTTP mock 网关 | MCP Server / Higress MCP 代理 | 仅协议适配（`mcp_server.py` 25 工具已实证零业务重构，`mcp_client_test.py` 12/12 断言含 25 工具全集精确校验） |
| TF-IDF RAG | PolarDB pgvector | 替换 `TFIDFRagIndex.search`，接口不变；**迁移 PoC 已完成**（三后端可插拔 + 14 查询等价性验证，见 [RAG_PGVECTOR_MIGRATION.md](RAG_PGVECTOR_MIGRATION.md)） |
| Agent 记忆 JSONL | PolarDB 长记忆 / 统一模型层 | 持久化替换，`recall_semantic` 接口不变 |
| AgentTeams 真实 LLM 推理驱动 | 多模型路由 / 自部署模型 / 更强调度策略 | 编排契约与 trace 结构不变；**真框架已跑**（11 容器 v1.1.2 + Matrix，2026-08-16 三场景全闭环，详见 `docs/RUN_EVIDENCE/AGENTTEAMS_REAL_RUN_EVIDENCE_20260816.md`）；三个 LLM 决策点已由百炼 LLM 自主驱动（`llm_client.py` + `llm_decision_demo.py`） |
| 网关 Trace + 审计 JSONL | LoongSuite / AgentScope Studio | 语义已对齐 OTel GenAI |

## 8. 文件索引

| 层 | 关键文件 | 说明 |
| --- | --- | --- |
| AgentTeams | `at/team_spec.json`, `at/AGENTTEAMS_RUNBOOK.md` | 编排契约 + 运行手册 |
| Agent 定义 | `agents/*.md`, `docs/方案详述.md` 附录 A | 8 Agent Identity |
| Skill | `skills/*/SKILL.md`, `docs/方案详述.md` 附录 B | 13 Skill（11 自定义 + evidence-archive/sms-approval-alert 2 个官方用云） |
| 工具 | `tools/mock_tools.py`, `tools/mock_tool_server.py`, `tools/mcp_server.py` | 业务逻辑 + 网关（含故障注入框架）+ MCP（25 工具） |
| LLM 决策 | `tools/llm_client.py`, `tools/llm_decision_demo.py` | 三个 LLM 自主决策点（审批门禁 + 车型推荐 + 工具顺序） |
| Agent 层评估 | `tools/agent_eval.py` | Agent 决策层评估（transcript vs Golden）+ LLM-as-Judge（DEAL-2002/2003） |
| 三层 trace 树 | `tools/agent_span_builder.py` | Agent→Skill→Tool 三层树构建 + 链路完整性校验（`--check-only`） |
| RAG/记忆 | `tools/mock_tools.py`(TFIDFRagIndex + recall_semantic), `tools/vector_rag.py`, `tools/pgvector_migration/DDL.sql` | 三后端可插拔向量检索（tfidf/embedding/pgvector）+ 记忆存储 + pgvector 迁移 DDL |
| 韧性验证 | `tools/fault_injection_test.py` | 故障注入测试（4 故障类型 × 7 用例 52 断言，降级/重试/隔离/恢复） |
| 评估 | `tools/eval_harness.py`, `tools/selfcheck.py` | Golden/Badcase + 自检 |
| 证据归档 | `tools/evidence_archive.py`, `tools/sms_alert.py` | OSS / 阿里云短信 2 个官方用云 Skill 等价实现 |
| 接口契约 | `docs/INTERFACE_CONTRACT.md`, `tools/MCP_MAPPING.md`, `tools/tool_catalog.json` | 等价 MCP 集成契约（11 域 25 函数） |
| 证据 | `docs/EVIDENCE.md`, `docs/RUN_EVIDENCE/` | 35 项可复现证据 E1-E35（含 AgentTeams 真框架三场景全闭环 + RAG pgvector PoC + 故障注入 + DEAL-2004 复合场景离线重放） |
