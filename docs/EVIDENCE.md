# 运行证据索引（EVIDENCE）

> 面向评审：本文件汇总 CarSales agentteams-demo 的可复现运行证据。所有证据均可在本地 3 步内复现。

## 1. 运行环境

- 操作系统：macOS（Darwin）/ Linux 均可（纯 Python 3 标准库，无第三方依赖）。
- 运行入口：`python3 tools/mock_tool_server.py --host 0.0.0.0 --port 18089`（HTTP mock 工具网关）。
- 自检入口：`python3 tools/selfcheck.py`（离线自检，无需启动网关）。
- AgentTeams 完整运行手册：见 `at/AGENTTEAMS_RUNBOOK.md`（含 Docker/Element Web 逐步指引）。

## 2. 核心证据清单

| # | 证据 | 文件 / 复现命令 | 结论 |
|---|---|---|---|
| E1 | 工程自检报告（3 场景 + 审计闭环 × 56 项断言） | `docs/selfcheck_report.txt`（`python3 tools/selfcheck.py` 生成） | **56/56 通过（56 passed, 0 failed）** |
| E2 | 多渠道会话归并 | selfcheck 断言：官网+企微+电话 3 条会话归并为 1 条线索 | 通过 |
| E3 | 报价计算正确性 | selfcheck 断言：`round(329800 - 329800*0.008 - 8000, 2)` 与政策一致 | 通过 |
| E4 | 低风险自动执行（L1） | selfcheck 断言：试驾预约自动成功、标准报价自动输出 | 通过 |
| E5 | 高风险审批门禁（L2） | selfcheck 断言：超授权优惠生成 discount_override 审批任务，订单仅草稿 | 通过 |
| E6 | 订单幂等与回滚 | selfcheck 断言：order_key 幂等；审批驳回 → confirm 门禁拦截 → 显式 rollback 到 draft | 通过 |
| E7 | 议价底线守护 | selfcheck 断言：触底停止让步、输出转人工交接单、重复大额让步不放行 | 通过 |
| E8 | RAG 案例沉淀与检索 | selfcheck 断言：成交案例脱敏入库并可检索召回 | 通过 |
| E9 | 全链路 Trace 留痕 | selfcheck 断言：单场景 Trace ≥ 10 条；运行期可用 `curl http://127.0.0.1:18089/tools/family_suv_deal/tools/trace` 查看 | 通过 |
| E10 | AgentTeams 编排材料 | `at/team_spec.json`（8 Worker + TeamLeader + 10 步 workflow + 风险策略）、`at/create_agents_messages.md`、`at/run_demo_task_message.md` | 齐备 |
| E11 | 治理材料 | `at/nacos_registry_mock.json`（Prompt/Skill/AgentSpec/Team 注册 + FORMAL 门禁 + 审计策略） | 齐备 |
| E12 | RAG 回归重放证据 | `docs/RUN_EVIDENCE/RAG_regression_replay.json`（`python3 tools/rag_regression_replay.py` 生成） | 真实 Trace 中 19 条空结果 RAG 查询：18 条为 AND 匹配缺陷、经加权 OR 修复后重放全部命中；1 条合法空（`零跑C16` 不在该场景 KB）；残留缺陷 0 |
| E13 | 可观测三端点（Trace+Log+Metrics） | `GET /tools/{sid}/tools/trace`、`/logs`、`/metrics`（`python3 tools/mock_tool_server.py` 运行） | OTel-GenAI 风格 span（trace_id/span_id/span_kind/status/duration_ms/parent_span_id）+ 结构化 Log（决策/审批/失败，trace_id 关联）+ Metrics（调用数/成功率/时延/按工具按类型） |
| E14 | MCP Server（协议适配实证） | `tools/mcp_server.py`（FastMCP stdio，22 工具复用 LocalMockTools）、`tools/mcp_client_test.py`（`python3 tools/mcp_client_test.py`）、`docs/RUN_EVIDENCE/mcp_e2e_evidence.json`（结构化运行证据） | **9/9 通过**：initialize / tools/list / 5 次 tools/call 全部成功；证明 HTTP 工具目录迁移到 MCP **仅需协议适配**（`_STATE_CACHE` 保持 quote/order 跨调用状态，业务逻辑零重构）；新增 approval_approve/reject/check、order_confirm、audit_query 5 工具覆盖审批决策闭环 |
| E15 | 评估闭环（Golden/Badcase + LLM-as-Judge） | `tools/eval_harness.py`（`python3 tools/eval_harness.py`，配 .env 自动激活 LLM-as-Judge）、`docs/RUN_EVIDENCE/eval_report.json` | Golden 准确率 **13/13=1.0**、守卫精确率 **7/7=1.0**、综合 **1.0**，按 16 维度全 1.0；新增 G13 审批闭环（approve→confirm→won）、B07 驳回→门禁拦截→回滚→审计留痕；**LLM-as-Judge 已 online**（百炼 qwen-plus）：tool_selection **10/10**、risk_compliance **10/10**、rag_relevance **9/10**，评语"教科书级闭环执行" |
| E16 | 官方用云 Skill：OSS 证据归档（真 REST 调用 + 本地降级） | `tools/evidence_archive.py`（OssObjectStore 真 OSS REST + LocalObjectStore 降级）、`skills/evidence-archive/SKILL.md`、`docs/OFFICIAL_SKILL_INTEGRATION.md`；端点 `POST /tools/{sid}/archive` | **P3.2 升级**：OssObjectStore 从注释代码升级为真阿里云 OSS REST 调用（OSS v1 HMAC-SHA1 签名，stdlib hmac/hashlib/base64，**零 oss2 SDK 依赖**）——有 `OSS_ACCESS_KEY_ID/SECRET` 真调 OSS PUT/GET/list，无凭证降级 LocalObjectStore；`store_type` 字段诚实标注 `oss_rest`/`local`；归档 key 含 trace_id 可审计回溯，`/archive` 返回 status/etag/size/store_type/backend，`/logs` 记录 `evidence_archived`+`store_type` |
| E17 | 可运行 Demo：实时网关面板 | `demo/src/components/LiveGateway.jsx`、`demo/src/lib/gatewayClient.js`、`demo/src/data/liveScripts.js`（`cd demo && npm run dev`） | 三场景 AgentTeams 管线协同全绿（**17/8/11 步**），`{{quote_id}}`/`{{slot}}`/`{{plan_id}}` 变量注入正确；Trace/Logs/Metrics 三面板从 live 网关拉取；traceparent 传播 **trace_id+parent_span_id**（OTel trace 树一致），`/archive` 一键归档 |
| E18 | 安全审计闭环（审批→回滚→审计） | `tools/mock_tools.py`（approve/reject/confirm_order/audit_trail）、`tools/mock_tool_server.py`（`/audit` 端点 + append-only 审计 JSONL）、`tools/llm_decision_demo.py`（三安全分支演示） | 三安全分支端到端：**DEAL-2001 reject→rollback（rolled_back）**、**DEAL-2002 approve→confirm（won）**、**DEAL-2003 pending→human_handoff（禁止默认放行）**；审计轨迹 6/4/4 条 action 全量留痕、`trace_id` 关联、append-only 落盘；MCP 5 工具 + HTTP `/audit` 端点可按 approval_id/order_id 筛选 |
| E19 | LLM 自主审批决策（TeamLeader 审批门禁，决策点 1） | `tools/llm_client.py`（百炼 LLM 决策客户端 + 忠实 prompt + .env 加载）、`tools/llm_decision_demo.py`（独立演示）、`.env.example`、`docs/RUN_EVIDENCE/llm_decision_*.json` | TeamLeader 审批门禁由百炼 LLM（qwen-plus，可切 qwen-max）**基于忠实业务上下文自主推理**——prompt 只给事实（金额/授权底线/客户/召回/证据材料状态），不操纵决策方向；**三分支分化对齐**：DEAL-2001 reject / DEAL-2002 approve / DEAL-2003 pending，`decision_source=llm` 全程标注；无 key 降级 `fallback_config`；`raw_response` 可回放 |
| E20 | OTel 真落地：hand-written span → 真 OpenTelemetry SDK 导出 | `tools/otel_exporter.py`（`python3 tools/otel_exporter.py`）、`docs/RUN_EVIDENCE/otel_sdk_spans.jsonl`（95 span）、`docs/RUN_EVIDENCE/otel_sdk_export_summary.json` | **opentelemetry-sdk 1.27.0** TracerProvider + Resource（service.name=carsales-agentteams）+ BatchSpanProcessor + ConsoleSpanExporter + FileSpanExporter；把工具网关 hand-written span 重放为真 OTel SDK Span——**95 span 全导出**（3 trace），parent 链接正确（OTel SDK parent_id）；**GenAI semconv 全覆盖**：`gen_ai.system=dashscope` / `gen_ai.agent.name` / `gen_ai.tool.name` / `gen_ai.request.model=qwen-plus` / `gen_ai.operation.name=rag_query`；resource 含 telemetry.sdk.name=opentelemetry |
| E21 | 第二个 LLM 决策点：strategy_planner 车型推荐自主评估 | `tools/llm_client.py`（`RECOMMENDATION_PROMPT` + `recommend()` 方法）、`tools/llm_decision_demo.py`（独立演示）、`docs/RUN_EVIDENCE/llm_decision_*.json` | strategy_planner 车型推荐由百炼 LLM **自主评估匹配度**——LLM 不选车型（车型由库存匹配规则选定），只自主输出「为什么这车型适合这客户」+ `fit_confidence` + `risk_flag`；**诚实分化**：DEAL-2001 fit=high / DEAL-2002 **fit=medium risk=preference_mismatch** / DEAL-2003 fit=high；prompt 忠实，不操纵；`decision_source=llm` 全标注；无 key 降级 `fallback_config` |
| E22 | **AgentTeams 真框架运行证据**（两轮真跑：8/14 单场景完整 DAG + 8/16 三场景全天闭环） | 第二轮（主证据）：`docs/RUN_EVIDENCE/AGENTTEAMS_REAL_RUN_EVIDENCE_20260816.md`（11 容器 v1.1.2 + **三场景 8 节点 DAG 全闭环** + 3 份 complete_project 报告 + 116 次工具调用 100% 成功 + 3.2MB transcript）；第一轮：`AGENTTEAMS_REAL_RUN_EVIDENCE.md`（127 条 transcript + Worker 日志） | **真 AgentTeams v1.1.2 Docker 框架运行**（非概念映射）：2026-08-16 当天 DEAL-2001/2002/2003 依次端到端闭环（16:46/17:46/18:34），每场景均触发 L2 风控审批且系统正确停止让利/转人工；4 类运行故障（mention 过滤/假派发/超时/空回合）全部根因分析+代码级修复+回归验证（见 E26） |
| E23 | 第三个 LLM 决策点：strategy_planner 工具调用顺序自主规划 | `tools/llm_client.py`（`TOOL_PLANNING_PROMPT` + `plan_tool_calls()` 方法）、`tools/llm_decision_demo.py`（独立演示）、`docs/RUN_EVIDENCE/llm_decision_*.json` | strategy_planner 的 4 个工具调用顺序由百炼 LLM **自主规划**；**诚实分化**：DEAL-2001/2002 → `list_models→check_stock→get_policy→calc_quote` / DEAL-2003 → **`list_models→get_policy→check_stock→calc_quote`**（LLM 把 get_policy 提前）；`decision_source=llm` 全标注，`planning_reason` 留痕可审计；无 key 降级固定顺序 `fallback_config` |
| E24 | 工具网关 OTel 可观测能力 | `tools/otel_exporter.py`（`init_runtime_otel()` 函数，工具网关可集成）、`tools/mock_tool_server.py`（网关 Trace/Log/Metrics 三端点） | 工具网关已具备 OTel 可观测集成能力：`init_runtime_otel()` 可在网关运行时导出真 OTel SDK span；网关 `/trace` `/logs` `/metrics` 三端点已覆盖 OTel-GenAI 风格 span + 结构化 Log + Metrics；Agent/Skill/LLM 层 span 由 AgentTeams 运行时或 LoongSuite/AgentScope Studio 采集（复赛接入） |
| E25 | OSS REST 代码端到端验证（签名正确 + MinIO PUT/GET 往返） | `docs/RUN_EVIDENCE/oss_rest_verification.json`、`tools/evidence_archive.py`（`OssObjectStore._sign`/`put_object`/`get_object`） | **刀4 验证**：①签名正确性验证通过；②REST 往返 MinIO PUT/GET 成功；③无 OSS 凭证 → `store_type=local` 诚实降级；配置凭证后 → `store_type=oss_rest` 真调阿里云 OSS REST |
| E26 | **三场景异常分支与自愈工程**（真实运行可靠性） | `docs/RUN_ISSUES_AND_SOLUTIONS.md`（问题清单+方案）、`tools/patch_mention_filter.py`（框架级 mention 过滤补丁，幂等）、`tools/apply_mention_patch*.sh`、`tools/recover_*.sh`（超时/空回合恢复范式） | 4 类真实故障全部闭环：①Worker 完成报告被 mention 过滤静默丢弃 → **代码级根治**（TASK_* 协议消息免过滤，Leader+8 Worker 应用，DEAL-2003 后半程零人工干预验证）；②Leader 假派发 → 固化两步派发规则；③MODEL_TIMEOUT 900s → 强制小步执行恢复范式；④NO_REPLY 空回合 → 重发强制报告范式。异常处置本身构成可复用的多 Agent 运维能力 |

## 3. 复现步骤

```bash
# 1. 离线自检（无需任何外部依赖，3 场景 + 审计闭环 × 56 项断言）
python3 tools/selfcheck.py

# 2. LLM 自主决策演示（三个决策点：审批门禁 + 车型推荐 + 工具顺序）
#    无 .env key → 决策降级 fallback_config
python3 tools/llm_decision_demo.py

# 2b.（可选，自主决策铁证）配置百炼 key 后，三个决策点由 LLM 自主推理
cp .env.example .env  # 填入 DASHSCOPE_API_KEY=sk-xxx（+ 可选 OSS_* 凭证）
python3 tools/llm_decision_demo.py   # 三个 LLM 决策点 decision_source=llm

# 2c.（可选，OTel 真落地）hand-written trace 重放为真 OTel SDK Span
python3 tools/otel_exporter.py   # 重放 95 span → 真 OpenTelemetry SDK 导出（ConsoleSpanExporter + GenAI semconv）

# 3. 启动工具网关并探活
python3 tools/mock_tool_server.py --host 0.0.0.0 --port 18089 &
curl http://127.0.0.1:18089/health

# 4. 查看场景全量 Trace（网关运行时）
curl http://127.0.0.1:18089/tools/family_suv_deal/tools/trace

# 5. 安全审计闭环（网关运行时）：审批决策 + 审计轨迹查询
#    驳回 -> 门禁拦截 -> 回滚 -> 审计留痕（完整链路）
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/mock_finance.reject \
  -H 'Content-Type: application/json' -d '{"approval_id":"APR-xxx","approver":"mgr","reason":"超底线"}'
curl http://127.0.0.1:18089/tools/family_suv_deal/audit              # 全量审计轨迹
curl "http://127.0.0.1:18089/tools/family_suv_deal/audit?approval_id=APR-xxx"  # 按审批单筛选

# 6. 可运行 Demo 面板（网关需先启动）：浏览器打开后切到「实时网关」Tab，
#    点击「运行实时演示」即可驱动 AgentTeams 管线并实时查看 Trace/Logs/Metrics + 一键归档
cd demo && npm install && npm run dev

# 7. MCP Server 验证（stdio JSON-RPC，22 工具，证明迁移只需协议适配）
python3 tools/mcp_client_test.py

# 8. 评估闭环（Golden/Badcase 规则评估 + LLM-as-Judge，配 .env 自动激活）
python3 tools/eval_harness.py

# 9. 证据归档（OSS 真 REST Skill，网关运行时；有 OSS 凭证真调 OSS，无凭证降级本地）
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/archive -d '{"deal_id":"DEAL-2001"}'
curl http://127.0.0.1:18089/tools/family_suv_deal/archives

# 10. AgentTeams 真框架运行（Docker 11 容器 + Matrix 协议 + 3 场景）
#     详见 at/AGENTTEAMS_RUNBOOK.md；证据见 docs/RUN_EVIDENCE/AGENTTEAMS_REAL_RUN_EVIDENCE.md
docker ps | grep hiclaw                    # 确认 11 个容器 Up（controller+manager+leader+8 worker）
#     通过 Matrix API 向 TeamLeader room 发送销售任务 → Leader ReAct agent 拆解 DAG → Worker 协同执行
#     127 条 room transcript（第一轮）+ 三场景全闭环 transcript（第二轮 2026-08-16）+ Worker 日志 + DAG plan.md + task meta.json 已归档
```

## 4. 三个 Demo 场景与期望信号

| 场景 | deal_id | 核心验证点 |
|---|---|---|
| `scenarios/family_suv_deal.json` | DEAL-2001 | 3 渠道归并 → 二胎家庭画像 → 车型对比 → 试驾 L1 + 报价 L1 → 超授权优惠 L2 审批 → 订单草稿 → check_deal |
| `scenarios/first_car_finance.json` | DEAL-2002 | 首购画像 → 月供敏感 → 2 组金融方案对比 → 征信授权 L2 审批门禁 → 合规边界说明 |
| `scenarios/trade_in_renewal.json` | DEAL-2003 | 3 年车主记忆召回 → 置换方案 → 议价触底转人工交接单 → 售后模板触达 → 案例脱敏入库 |

期望信号明细见 `at/AGENTTEAMS_RUNBOOK.md` 第 7 节「判断是否跑通」。

## 5. AgentTeams 运行工具调用证据（3 场景）

> **证据边界（诚实披露）**：以下 Trace 是 AgentTeams 真实运行期间、mock 工具网关记录的 **HTTP 工具调用层证据**，
> 证明 8 个 Worker 确实通过网络主动调用了 CRM/库存/报价/金融/试驾/订单/知识库/企微工具并完成业务闭环逻辑。
> Agent 层编排证据（TeamLeader 如何拆解任务 / Agent 间上下文如何传递 / LLM 推理输出）由 AgentTeams 运行时采集，
> 见 E22（第一轮 127 条 Matrix transcript + Worker 日志 + DAG plan；第二轮 2026-08-16 三场景全闭环 transcript）。
> 运行期 Mock 工具网关容器 IP 172.18.0.4:18089，Worker 通过容器网络访问。

### 5.1 运行汇总（两轮真跑）

**第二轮（2026-08-16，主证据，三场景全闭环）**

| DEAL | 场景 | 工具调用数 | 成功率 | Trace/Metrics/Audit 文件 |
|------|------|-----------|-------|-----------|
| DEAL-2001 | family_suv_deal | **56** | 100% | `RUN_EVIDENCE/trace_family_suv_deal_20260816.json` + `gateway_*_family_suv_deal_20260816.json` |
| DEAL-2002 | first_car_finance | **36** | 100% | `RUN_EVIDENCE/trace_first_car_finance_20260816.json` + `gateway_*_first_car_finance_20260816.json` |
| DEAL-2003 | trade_in_renewal | **24** | 100% | `RUN_EVIDENCE/trace_trade_in_renewal_20260816.json` + `gateway_*_trade_in_renewal_20260816.json` |
| **合计** | — | **116** | **100%** | 22 类工具全覆盖，含写操作链 reserve_car→create_order→check_deal 与审批链 submit_approval→check_approval |

**第一轮（2026-08-14，DEAL-2003 完整 DAG）**

| DEAL | 场景 | 工具调用数 | 覆盖工具数 | Trace 文件 |
|------|------|-----------|-----------|-----------|
| DEAL-2001 | family_suv_deal（二胎家庭 SUV 全链路成交） | 33 | 12 | `RUN_EVIDENCE/DEAL-2001_trace.json` |
| DEAL-2002 | first_car_finance（首购客户金融方案） | 24 | 11 | `RUN_EVIDENCE/DEAL-2002_trace_full.json` |
| DEAL-2003 | trade_in_renewal（老客户置换与售后运营） | 22 | 11 | `RUN_EVIDENCE/DEAL-2003_trace.json` |
| **合计** | — | **79** | **12** | — |

### 5.2 各场景工具调用明细

**DEAL-2001（family_suv_deal）— 33 次调用**
```
mock_crm.get_lead: 6          mock_knowledge.search_product: 3
mock_knowledge.search_sop: 5  mock_knowledge.search_case: 3
mock_price.calc_quote: 5      mock_inventory.check_stock: 3
mock_price.get_policy: 2      mock_finance.calc_plan: 2
mock_crm.list_sessions: 1     mock_crm.get_customer_history: 1
mock_inventory.list_models: 1 mock_testdrive.list_slots: 1
```
覆盖全链路：线索归并 → 画像构建 → 意图分析 → 策略规划 → 报价 → 金融方案 → 试驾预约

**DEAL-2002（first_car_finance）— 24 次调用**
```
mock_price.calc_quote: 6      mock_knowledge.search_case: 2
mock_crm.get_lead: 5          mock_price.get_policy: 2
mock_inventory.check_stock: 3 mock_crm.list_sessions: 1
mock_knowledge.search_product: 1 mock_crm.get_customer_history: 1
mock_knowledge.search_sop: 1  mock_inventory.list_models: 1
mock_finance.calc_plan: 1
```
覆盖：首购画像 → 金融方案对比（6 次报价计算）→ 征信授权 → 合规边界

**DEAL-2003（trade_in_renewal）— 22 次调用**
```
mock_crm.get_lead: 5          mock_price.calc_quote: 3
mock_knowledge.search_case: 3 mock_price.get_policy: 2
mock_inventory.check_stock: 2 mock_crm.list_sessions: 1
mock_wechat.get_session: 1    mock_knowledge.search_sop: 1
mock_knowledge.search_product: 1 mock_crm.get_customer_history: 1
mock_inventory.list_models: 1 mock_finance.calc_plan: 1
```
覆盖：老客户记忆召回 → 置换评估 → 议价触底 → 售后触达 → 案例入库

### 5.3 关键验证点达成

| 验证点 | DEAL | 证据 |
|--------|------|------|
| 多渠道会话归并（3 渠道 → 1 线索） | DEAL-2001 | `mock_crm.list_sessions` + `mock_crm.get_lead` 调用链 |
| 结构化画像 + 置信度 | DEAL-2001/2002/2003 | 各场景 `mock_crm.get_customer_history` + `mock_knowledge.search_case` |
| 意向评分与分级 | DEAL-2002 | intent-analyst 输出 P1 评分 7，BANT 3.5/4 |
| 金融方案对比 | DEAL-2002 | `mock_price.calc_quote` × 6 + `mock_finance.calc_plan` |
| 报价政策合规 | DEAL-2001/2002/2003 | `mock_price.get_policy` + `mock_price.calc_quote` 调用链 |
| 置换评估与议价底线 | DEAL-2003 | `mock_wechat.get_session`（老客户回访）+ 触底转人工 |
| 全链路 Trace ≥ 10 条 | 3 场景均满足 | 33 / 24 / 22 条 |

### 5.4 真实运行 RAG 空结果回归说明

真实运行 Trace 中存在 **19 条 RAG 查询返回 `[]`**（DEAL-2001 最多）。根因：当时 `mock_tools._match` 使用 AND 全词匹配，对 LLM 自然语言长句查询（如 `search_sop "成交信号"`、`search_product "新能源六座SUV 25万"`）命中率极低。事后已将 `_match` 升级为 **TF-IDF 余弦相似度向量检索**（`TFIDFRagIndex`，平滑 idf + 阈值 0.05 + Top-3），并补 selfcheck 回归断言（现 56/56）。

为消解"selfcheck 全绿 vs Trace 仍 19 空"的矛盾，提供可复现回归证据（E12）：把这 19 条空结果查询经修复后逻辑重放，结果 **18 条匹配缺陷全部命中、1 条为合法空**（`search_product "零跑C16"`——该场景 KB 无零跑车型，`[]` 是正确行为）、**残留缺陷 0**。

> 注：E12 是离线重放，证明修复有效；TF-IDF 检索为纯 Python 实现，后续可平滑迁移到 PolarDB pgvector（仅需替换 `TFIDFRagIndex.search` 为向量库查询，接口不变）。

## 6. 边界声明（诚实披露）

- 初赛交付为 **mock 环境下的任务级自主闭环**：工具网关为 HTTP mock 适配器（MCP 等价契约见 `tools/MCP_MAPPING.md`），非真实 CRM/DMS/金融系统。
- 复赛计划按 `docs/方案详述.md` 附录 F 推进真实系统接入与 AgentTeams 实际部署演示。
- ~~本次运行中 DEAL-2002 曾遇到 Leader 队列 idle 清理导致 Wave 3 未自动派发~~ → **已于 2026-08-16 根治**：根因为 copaw `_was_mentioned` 只认结构化 mention 且纯文本兜底参数传空串，`tools/patch_mention_filter.py` 对 TASK_* 协议消息免过滤后，DEAL-2003 后半程（intent→strategy→negotiation→order→ops→complete_project）全程零人工干预自动流转（E26）。同类异常（MODEL_TIMEOUT 900s、NO_REPLY 空回合）均有恢复范式沉淀，详见 `docs/RUN_ISSUES_AND_SOLUTIONS.md`。
- **可观测边界**：网关层已提供 OTel-GenAI 风格 span（tool/rag 类）+ 结构化 Log（决策/审批/失败）+ Metrics（E13）；W3C `traceparent` 现已同时传播 `trace_id` 与 `parent_span_id`（E17 验证：工具 span 与 Agent 层 span 同属一个 trace，trace 树一致），网关会话 id 作为 `gateway.session_id` 属性保留供 `/metrics` 关联。但 **Agent/Skill/LLM 层 span 不在网关职责内**，需 AgentTeams 运行时或 LoongSuite/AgentScope Studio 采集，复赛接入。
