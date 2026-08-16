# CarSales：基于多 Agent 的汽车销售自主成交智能助手（AgentTeams 最小可运行 Demo）

面向 GOAI「新智基座 | Agent Infra」赛题方向二（智能客服自主闭环）的汽车销售场景落地。用户只提供客户咨询与少量线索信息，AgentTeams 中的 8 个业务 LLM Agent 通过 HTTP mock 工具网关主动查询 CRM、库存、报价、金融、试驾、订单、知识库（RAG）与企业微信数据；创建 Team 时由 manager 创建独立 TeamLeader Worker `carsales-demo-leader` 负责调度协作，完成「线索获取 — 需求分析 — 成交促进 — 售后运营 — 知识沉淀」的零人工销售闭环。

完整运行手册见 [at/AGENTTEAMS_RUNBOOK.md](at/AGENTTEAMS_RUNBOOK.md)。

## Demo 要证明什么

1. AgentTeams 可以创建并管理 8 个职责明确的业务 LLM Agent，并在创建 Team 时生成 1 个独立 TeamLeader Worker。
2. Worker 在 Docker 中也能通过 HTTP 工具网关主动取证，不依赖宿主机目录。
3. 四个销售场景分四次独立处理，展示完整成交闭环、金融审批闭环、老客户运营闭环与置换+金融双审批复合联动闭环（DEAL-2004 为离线重放验证，见 EVIDENCE.md E34）。
4. 低风险动作（试驾预约、标准报价、模板消息）进入自动化执行语义；高风险动作（超授权优惠、征信授权、订单确认）只生成审批计划；议价触及底线停止让步并转人工。
5. 全链路工具调用可观测：每次调用写入 OTel-GenAI 风格 Span（trace_id/span_id/span_kind/status/duration_ms/parent_span_id）+ 结构化 Log + Metrics，W3C `traceparent` 传播 `trace_id`+`parent_span_id` 使工具 span 与 Agent span 同属一个 trace 树；离线由 `agent_span_builder.py` 构建 Agent→Skill→Tool 三层 trace 树（TeamLeader root，182 span，工具 span 挂载率 100%）。
6. 安全审计闭环：高风险动作（L2）禁止默认放行——`approve`/`reject` 决策驱动 `confirm_order`/`rollback_order`（决策与执行分离），`audit_trail` 全量留痕（append-only JSONL，trace_id 关联）；三安全分支端到端：驳回→回滚、通过→确认→成交、挂起→转人工。
7. 可运行验证闭环：离线自检（87 项断言 = 4 场景 + 审计闭环）+ LLM 自主决策演示（三个决策点）+ MCP Server（25 工具全集，迁移只需协议适配）+ Golden/Badcase 评估（13+7=1.0）+ Agent 决策层评估（命中率平均 0.9722）+ OSS 证据归档 + 短信审批告警 + 三后端可插拔 RAG（pgvector PoC）+ 故障注入测试（7 用例 52 断言）+ Agent 记忆 + 浏览器实时网关面板，全部本地可复现。
8. LLM 自主决策（三个决策点）：①TeamLeader 审批门禁由百炼 LLM 基于忠实业务上下文自主推理 approve/reject/pending；②strategy_planner 车型推荐由 LLM 自主评估匹配度 + 风险标记（DEAL-2002 诚实标 preference_mismatch）；③strategy_planner 工具调用顺序由 LLM 自主规划（DEAL-2003 LLM 把 get_policy 提前到 check_stock 之前，体现场景化编排）。`decision_source` 诚实标注 `llm`/`fallback_config`，无 key 仍 ALL PASS，reason/raw_response 留痕可回放——把「编排闭环」升级为「自主闭环」。
9. OTel 真落地 + 官方用云 Skill 真集成（2 个）：opentelemetry-sdk 1.27.0 重放导出 261 span（6 trace = 3 工具层 + 3 三层树；ConsoleSpanExporter + GenAI semconv：`gen_ai.system`/`agent.name`/`tool.name`/`request.model`）；OSS REST 签名已验证 + MinIO PUT/GET 往返成功（OSS v1 签名，有凭证真调、无凭证降级本地，`store_type` 诚实标注）；阿里云短信 Dysmsapi 真 REST 路径（RPC V1 签名，有凭证真调、无凭证降级本地外呼记录，`channel_type` 诚实标注）；百炼=真阿里云模型服务集成。

## Demo 场景

| 场景 ID | 场景 | 预期处置 |
| --- | --- | --- |
| `family_suv_deal` | 二胎家庭 SUV 购车，多渠道线索（官网+企微+电话） | 归并线索、构建画像、推荐车型、自动预约试驾、标准报价、超授权优惠生成 L2 审批、订单草稿、案例沉淀 |
| `first_car_finance` | 首购客户金融方案（短视频渠道） | 画像与意图识别、金融方案对比、征信授权生成 L2 审批、订单草稿（审批前不确认） |
| `trade_in_renewal` | 老客户置换 + 售后运营 | 历史画像 RAG 召回、置换方案测算、议价触及底线转人工、售后权益模板触达、复购沉淀 |
| `trade_in_finance` | 老客户置换升级高端 SUV + 金融分期（复合场景） | 历史画像召回、置换评估（授权内 L1 / 超授权估值上浮 L2 审批）、报价与缺口测算、金融方案对比、征信授权 L2 审批、叠加让步触底转人工、双审批齐备前订单禁止 confirm、交付关怀 |

## 核心 Agent（8 业务 Worker + 1 TeamLeader）

| Agent | 作用 | 关键 Skill | 工具 |
| --- | --- | --- | --- |
| CarSales TeamLeader | 创建 Team 时由 manager 生成的独立 Worker，名称固定为 `carsales-demo-leader` | 由 manager 创建 | 无直接工具调用 |
| Lead Intake | 多渠道会话归并去重分级 | `lead-fusion`, `profile-building` | `mock_crm`, `mock_wechat`, `mock_knowledge` |
| Profile Builder | 构建客户画像（预算/家庭/场景/偏好） | `profile-building`, `deal-memory` | `mock_crm`, `mock_knowledge` |
| Intent Analyst | 购车意图识别与跟进优先级 | `intent-scoring`, `deal-memory` | `mock_crm`, `mock_knowledge` |
| Strategy Planner | 车型推荐、报价与跟进路径 | `car-recommendation`, `quote-pricing`, `deal-memory` | `mock_inventory`, `mock_price`, `mock_knowledge`, `mock_crm` |
| Negotiation Executor | 试驾预约/报价/优惠/金融方案执行 | `quote-pricing`, `negotiation-guard`, `test-drive-booking`, `finance-plan` | `mock_price`, `mock_finance`, `mock_testdrive`, `mock_crm` |
| Order Executor | 订单草稿/状态/回滚/成交验证 | `order-safe-execute`, `deal-memory` | `mock_inventory`, `mock_order`, `mock_verify`, `mock_price` |
| Customer Ops | 售后触达/复购/转介绍 | `profile-building`, `deal-memory`, `case-mining` | `mock_crm`, `mock_wechat`, `mock_knowledge` |
| Knowledge Miner | 案例复盘与脱敏入库 | `case-mining`, `deal-memory` | `mock_knowledge`, `mock_crm` |

## 目录结构

```
carsales-demo/
├── agents/            # 8 个业务 Agent 定义（评审材料，附录 A 模板）
├── skills/            # 13 个可复用 Skill（11 自定义 + 2 官方用云：OSS 证据归档 / 短信审批告警）
├── tools/             # HTTP mock 工具网关 + 可观测 + MCP + 评估 + LLM 决策（根目录 16 个核心脚本）
│   ├── mock_tools.py             # 业务逻辑（11 域 25 函数，含 mock_tradein 置换评估）+ RAG + OTel span/log/metrics + approve/reject/confirm/audit
│   ├── mock_tool_server.py        # HTTP 网关（traceparent 传播 + /trace /logs /metrics /audit /archive + FAULT_INJECTION 故障注入框架）
│   ├── mcp_server.py             # FastMCP stdio Server（25 工具，复用 LocalMockTools）
│   ├── mcp_client_test.py        # MCP 端到端验证（12 断言：25 工具全集精确断言 + 短信幂等闭环）
│   ├── vector_rag.py             # RAG 三后端可插拔（local_tfidf / local_embedding / pgvector）+ 等价性验证 --equivalence
│   ├── fault_injection_test.py   # 故障注入测试（4 故障类型 × 7 用例 52 断言，非 happy path 韧性证据）
│   ├── llm_decision_demo.py     # LLM 自主决策能力独立演示（三个决策点，基于真实 AgentTeams 场景数据）
│   ├── llm_client.py             # 百炼 LLM 决策客户端（审批门禁 + 车型推荐 + 工具调用顺序三个决策点 + .env 加载 + 降级）
│   ├── eval_harness.py           # Golden/Badcase 评估 + LLM-as-Judge 模板
│   ├── agent_eval.py             # Agent 决策层评估（transcript 工具序列 vs Golden + LLM-as-Judge + DEAL-2004 离线重放）
│   ├── agent_span_builder.py     # Agent→Skill→Tool 三层 trace 树构建 + 链路完整性校验（--check-only）
│   ├── evidence_archive.py       # OSS 真调用证据归档 Skill（OssObjectStore 真 REST + LocalObjectStore 降级）
│   ├── sms_alert.py              # 阿里云短信审批告警 Skill（真 Dysmsapi REST + 本地降级）
│   ├── otel_exporter.py           # OTel 真落地：hand-written span → opentelemetry-sdk 真导出 + GenAI semconv
│   ├── rag_regression_replay.py  # 真实 Trace RAG 空结果回归重放
│   ├── selfcheck.py              # 离线自检（87 项断言 = 4 场景 + 审计闭环，56+31）
│   ├── pgvector_migration/       # PolarDB pgvector 迁移 DDL（2 表 + 2 函数 + HNSW 索引 + 角色权限）
│   ├── ops/                      # 一次性运维脚本归档（73 个，mention 补丁/故障恢复/证据采集，见 ops/README.md，不参与运行时）
│   ├── tool_catalog.json         # 工具目录与 MCP 映射（11 域 25 函数）
│   └── MCP_MAPPING.md            # 等价 MCP 集成契约
├── demo/              # React 前端 Demo（实时网关面板）
│   └── src/ components/LiveGateway.jsx, lib/gatewayClient.js, data/liveScripts.js
├── scenarios/         # 4 个销售场景数据（含预期结果；DEAL-2004 为复合场景，离线重放验证）
├── at/                # AgentTeams 协同层
│   ├── create_agents_messages.md   # 8 Worker + Team 完整创建消息
│   ├── team_spec.json              # Team 拓扑与工作流
│   ├── run_demo_task_message.md    # 3 个销售任务消息
│   ├── AGENTTEAMS_RUNBOOK.md       # 运行手册
│   ├── agentteams.env.example
│   ├── nacos_registry_mock.json    # AI 资源治理 mock
│   └── AgentTeam.md                # Team 形态说明
└── docs/              # 评审与演进文档（EVIDENCE.md / OFFICIAL_SKILL_INTEGRATION.md / 方案详述.md）
```

## 快速开始

### 环境要求

- Python 3.11+（核心业务零第三方依赖，纯标准库）
- 可选：`pip install -r requirements.txt`（OTel 可观测 + MCP Server，未安装自动降级不影响运行）

### 30 秒本地验证（零依赖，无 API Key）

```bash
cd <DEMO_DIR>

# 1. 离线自检：87 项断言（4 场景 + 审计闭环 = 56 + DEAL-2004 复合场景 31）
python3 tools/selfcheck.py
# → RESULT: 87 passed, 0 failed

# 2. LLM 自主决策演示：三个决策点（审批门禁 + 车型推荐 + 工具顺序）
python3 tools/llm_decision_demo.py
# → 3 场景三分支演示，decision_source=llm/fallback_config
# → 生成 docs/RUN_EVIDENCE/llm_decision_*.json

# 3. 评估闭环：Golden 13 + Badcase 7 = 1.0
python3 tools/eval_harness.py
# → Score: 1.0 (16 维度全 1.0)
```

> 无 API Key 时，三个 LLM 决策点自动降级 `decision_source=fallback_config`。

### 可选：配置百炼 LLM（三个决策点自主推理）

```bash
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY=sk-xxx
python3 tools/llm_decision_demo.py
# → decision_source=llm，三分支由 LLM 推理得出 + reason/raw_response 留痕
python3 tools/eval_harness.py
# → LLM-as-Judge online（产出评判 JSON）
```

### 可选：OTel 真落地（重放导出）

```bash
pip install opentelemetry-sdk opentelemetry-semantic-conventions

# 重放导出：工具网关 hand-written span + 三层 trace 树重放为真 OTel SDK Span
python3 tools/otel_exporter.py
# → docs/RUN_EVIDENCE/otel_sdk_spans.jsonl（261 span = 3 工具层 trace + 3 三层树，agent/skill/tool/rag）+ ConsoleSpanExporter
```

### 可选：Agent 层评估 + 三层 Trace 树校验（零依赖）

```bash
python3 tools/agent_eval.py
# → Agent 层工具选择命中率 1.0/1.0/0.9167（平均 0.9722）+ 顺序约束 12/12 + RAG 覆盖 1.0×3
# → 配 .env（DASHSCOPE_API_KEY）时 DEAL-2002/2003 由百炼真实 LLM-as-Judge 评判（judge_source=llm）

python3 tools/agent_span_builder.py --check-only
# → 三场景三层 trace 树链路完整性校验（工具 span 挂载率 100%）
```

### 可选：浏览器实时网关面板

```bash
# 启动 mock 工具网关
python3 tools/mock_tool_server.py --host 0.0.0.0 --port 18089 &

# 启动前端
cd demo && npm install && npm run dev
# → 浏览器打开「实时网关」Tab，回放管线 + Trace/Logs/Metrics + 归档
```

### 可选：MCP Server 验证

```bash
pip install mcp
python3 tools/mcp_client_test.py
# → 12/12 通过：25 工具全集精确断言 + sms_approval_alert 幂等闭环，证明迁移 MCP 只需协议适配
```

### 可选：RAG 三后端等价性 + 故障注入测试（零依赖）

```bash
# RAG pgvector 迁移 PoC：local_tfidf / local_embedding / pgvector 三后端 14 查询对比
python3 tools/vector_rag.py --equivalence
# → 生产后端 8/8 回归非空守护 + TF-IDF 空结果 9/9 被稠密链路修复 + 双非空 Top-3 overlap 1.0
# → 生成 docs/RUN_EVIDENCE/rag_backend_equivalence.json（迁移方案见 docs/RAG_PGVECTOR_MIGRATION.md）

# 故障注入：timeout / http_500 / empty_result / auth_error × 7 用例 52 断言
python3 tools/fault_injection_test.py
# → 降级契约（HTTP 200 + 结构化 degraded）/ 瞬时故障重试恢复 / 故障隔离 / 注入关闭零痕迹
# → 生成 docs/RUN_EVIDENCE/fault_injection_report.json
```

### AgentTeams 真框架运行（三个场景，需 Docker）

以下为 AgentTeams v1.1.2 Docker 框架的完整运行流程，逐个跑完三个销售场景。

#### 步骤 1：启动 Mock 工具网关

```bash
cd <DEMO_DIR>
python3 tools/mock_tool_server.py --host 0.0.0.0 --port 18089
```

另开终端验证：

```bash
curl http://127.0.0.1:18089/health
# → {"ok": true, ...}
```

#### 步骤 2：安装 AgentTeams

```bash
bash <(curl -sSL https://higress.ai/hiclaw/install.sh)
```

按安装器引导完成配置（关键项）：

| 引导项 | 样例值 |
| --- | --- |
| 版本 | `v1.1.2` |
| LLM | `qwen3.7-plus`（或可用模型） |
| API 联通性 | **必须测试通过** |
| Manager/Worker 运行时 | `qwenpow`（`copow`/`QwenPaw`） |
| Element Web 端口 | 默认 `18088` |
| Matrix E2EE | 建议禁用 |

安装完成后检查：

```bash
docker ps | grep hiclaw
# → 应看到 11 个容器（manager + 8 worker + element-web + minio + ...）
```

打开 Element Web：`http://127.0.0.1:18088`

#### 步骤 3：确定 Docker 容器可访问的工具网关地址

macOS Docker Desktop 中，容器访问宿主机服务需使用 `host.docker.internal`（而非 gateway IP `172.18.0.1`，后者是 VM 内部网桥，不等于宿主机）。

验证：

```bash
docker exec -it hiclaw-manager curl -s http://host.docker.internal:18089/health
# → {"ok": true, "service": "carsales-mock-tool-gateway"}
```

`<MOCK_TOOL_BASE_URL>` = `http://host.docker.internal:18089`

#### 步骤 4：创建 8 个 Agent + Team（一次性发送）

打开 [at/create_agents_messages.md](at/create_agents_messages.md)，将**全部内容**复制到 Element Web 的 `manager` 房间发送一次即可。消息内已包含 8 个业务 Worker 和 1 个 Team 的完整定义，manager 会按顺序逐个创建。

> 创建完成后，`manager` 会返回 Team 房间名称和 `team_leader_name`，记下来用于步骤 5。

#### 步骤 5：逐个发送三个销售任务

在 Element Web 会话列表中找到名称以 **`Team`** 开头、对应 `carsales-demo` 的 Team 房间。

**发送流程**：

1. 在 Team 房间输入框输入 `@<team_leader_name>`（选中 TeamLeader），然后粘贴任务内容发送
2. **等待完成**：等前一个 DEAL 报告完整输出后，再发下一个。不要同时发多条

> TeamLeader 会自动拆解任务并分配给对应的 Worker，Worker 之间通过 Team 房间协同工作，无需单独给每个 Agent 发消息。

---

**任务 1：DEAL-2001 — 二胎家庭 SUV 全链路成交**

```text
@<team_leader_name>

请让你的 Team 处理一条新的销售线索。

deal_id: DEAL-2001
scenario_id: family_suv_deal
deal_type: new_deal
门店：杭州滨江旗舰店
客户渠道：官网在线咨询 + 企业微信 + 电话

客户咨询（09:40 官网）：
家里刚有二宝，想换一辆大空间 SUV，预算 25 万左右，主要看新能源。平时带两个孩子自驾游比较多，安全配置要好。请问有什么推荐？

补充信息（10:05 企业微信）：
销售顾问问六座还是七座，客户回复五座以上都行，最好是六座，父母偶尔一起出门。
补充信息（10:20 电话转写）：
客户提到周末想去门店看实车，问试驾要不要预约。

请开始处理这条销售线索，推进到可成交状态，并输出本次销售闭环报告。
```

预期结果：线索归并 → 画像（二胎/25-28万/六座）→ 车型推荐 → 试驾预约（L1自动）→ 报价（L1自动）→ 超授权优惠 L2 审批 → 订单草稿 → 案例沉淀

---

**任务 2：DEAL-2002 — 首购客户金融方案**（等 DEAL-2001 报告完成后再发）

```text
@<team_leader_name>

请让你的 Team 处理一条新的销售线索。

deal_id: DEAL-2002
scenario_id: first_car_finance
deal_type: finance
门店：上海虹桥店
客户渠道：抖音私信 + 电话

客户咨询（14:05 抖音私信）：
刚毕业两年，想买第一辆车，预算 12 万到 15 万，想分期买，最好月供低一点。新能源还是油车还没想好，想听建议。

补充信息（14:30 电话转写）：
客户询问分期首付比例和月供，提到自己征信没问题、收入证明齐全，希望尽快锁定优惠。

请开始处理这条销售线索，重点输出金融方案与审批路径，并输出本次销售闭环报告。
```

预期结果：画像（首购/12-15万/月供敏感）→ 金融方案对比（厂家低息 2.99% vs 银行 3.99%）→ 征信授权 L2 审批 → 订单草稿（审批前不确认）

---

**任务 3：DEAL-2003 — 老客户置换与售后运营**（等 DEAL-2002 报告完成后再发）

```text
@<team_leader_name>

请让你的 Team 处理一条新的销售线索。

deal_id: DEAL-2003
scenario_id: trade_in_renewal
deal_type: trade_in
门店：广州天河店
客户渠道：企业微信（老客户回访）+ 门店

客户咨询（16:20 企业微信）：
你好，我是你们 3 年前买秦PLUS 的老车主陈先生。现在家里想换个大点的车，你们有什么置换政策？旧车能评估多少钱？另外我 3 月份车险到期了，之前的售后权益还能用吗？

补充信息（16:45 门店记录）：
陈先生到店看中大型 SUV，提出旧车置换 + 要求 3 万元额外优惠。

请开始处理这条销售线索，注意老客户权益与议价底线，并输出本次销售闭环报告。
```

预期结果：历史画像 RAG 召回 → 置换方案（旧车 9.8 万 + 补贴 1.2 万）→ 议价触底线转人工 → 售后权益模板发送（L1）→ 案例脱敏入库

---

#### 步骤 6：查看运行证据

每个场景跑完后，查看可观测数据：

```bash
# Trace（工具调用链路）
curl http://127.0.0.1:18089/tools/family_suv_deal/tools/trace
curl http://127.0.0.1:18089/tools/first_car_finance/tools/trace
curl http://127.0.0.1:18089/tools/trade_in_renewal/tools/trace

# Log（决策/审批事件）
curl http://127.0.0.1:18089/tools/family_suv_deal/logs

# Metrics（调用统计）
curl http://127.0.0.1:18089/tools/family_suv_deal/metrics

# Audit（审计轨迹）
curl http://127.0.0.1:18089/tools/family_suv_deal/audit
```

> 如果 Agent 要求你人工提供车型/库存/政策信息，提醒它：「请通过已配置的 HTTP mock 工具网关主动查询，不要让我人工收集完整证据。」

## 本地可运行验证（无需 AgentTeams）

除上述 AgentTeams 真实运行外，以下能力均可在本地独立复现（纯 Python 标准库 + Node）：

| 验证 | 命令 | 证据 |
| --- | --- | --- |
| 离线自检 | `python3 tools/selfcheck.py` | **87/87 断言通过**（4 场景 + 审计闭环 = 56 + DEAL-2004 复合场景 31） |
| LLM 自主决策演示 | `python3 tools/llm_decision_demo.py` | 三个 LLM 决策点（审批门禁 + 车型推荐 + 工具顺序）独立演示；`decision_source`=llm/fallback_config；三分支对齐（reject→rollback / approve→confirm / pending→human_handoff）；证据含完整上下文 + LLM 原始返回 |
| OTel 真落地 | `python3 tools/otel_exporter.py` → `otel_sdk_spans.jsonl` | **重放 261 span**（6 trace = 3 工具层 + 3 三层树 → 真 OTel SDK 导出）；opentelemetry-sdk 1.27.0 + GenAI semconv（`gen_ai.system`/`agent.name`/`tool.name`/`request.model`） |
| MCP Server | `python3 tools/mcp_client_test.py`（需 `pip install mcp`） | **12/12 通过**：25 工具全集精确断言（missing/extra 双向防漂移）+ sms_approval_alert 幂等闭环，证明迁移 MCP 只需协议适配 |
| RAG 三后端等价性 | `python3 tools/vector_rag.py --equivalence` | local_tfidf / local_embedding / pgvector 三后端 14 查询对比：生产后端 8/8 回归非空守护 + TF-IDF 空结果 9/9 被稠密链路修复 + 双非空 Top-3 overlap 1.0；迁移方案见 [docs/RAG_PGVECTOR_MIGRATION.md](docs/RAG_PGVECTOR_MIGRATION.md) |
| 故障注入测试 | `python3 tools/fault_injection_test.py` | 4 故障类型（timeout/http_500/empty_result/auth_error）× 7 用例 52 断言全过：结构化降级不抛 5xx、瞬时故障重试恢复、故障按工具隔离、注入留痕三处（span/audit/log）、未设置 FAULT_INJECTION 行为与原版一致 |
| 评估闭环 | `python3 tools/eval_harness.py` | Golden 13/13 + Badcase 7/7，综合 1.0（16 维度全 1.0）+ LLM-as-Judge online |
| Agent 层评估 | `python3 tools/agent_eval.py` | transcript 工具序列 vs 场景 Golden：命中率 1.0/1.0/0.9167（平均 0.9722）+ 顺序约束 12/12 + RAG 覆盖 1.0×3；配 key 时 DEAL-2002/2003 真实百炼 LLM-as-Judge |
| 三层 Trace 树 | `python3 tools/agent_span_builder.py --check-only` | Agent→Skill→Tool 三层树（TeamLeader root，182 span），工具 span 挂载率 100%，12/116 二级推导显式标注 |
| 安全审计闭环 | `curl …/tools/{sid}/mock_finance.reject` → `/audit` | approve/reject→confirm/rollback→audit_trail 端到端，append-only 审计 JSONL |
| 实时网关面板 | `python3 tools/mock_tool_server.py &` → `cd demo && npm run dev` | 浏览器「实时网关」Tab 回放管线 + Trace/Logs/Metrics + 归档 |
| 证据归档（OSS 真调用） | `curl -X POST …/tools/family_suv_deal/archive -d '{"deal_id":"DEAL-2001"}'` | OssObjectStore 真阿里云 OSS REST（v1 签名），有凭证真调/无凭证降级本地，`store_type` 标注 |
| 短信审批告警（真 REST 路径） | `curl -X POST …/tools/family_suv_deal/mock_sms.send_approval_alert -d '{"approval_id":"APR-xxx",…}'` | AliyunSmsSender 真阿里云 Dysmsapi REST（RPC V1 签名），有凭证真调/无凭证降级本地外呼记录，`channel_type` 标注；alert_key 幂等 |
| **AgentTeams 真框架运行** | `docker ps \| grep hiclaw` → Matrix API 发任务 → 查 room transcript | **11 容器 v1.1.2 真 Docker 运行**（非概念映射）：**2026-08-16 一天内 3 场景全闭环**（24 节点 DAG 全绿 + 116 次工具调用 100% 成功 + 3 份 complete_project 报告），证据见 [docs/RUN_EVIDENCE/AGENTTEAMS_REAL_RUN_EVIDENCE_20260816.md](docs/RUN_EVIDENCE/AGENTTEAMS_REAL_RUN_EVIDENCE_20260816.md) |
| **异常分支与自愈** | `tools/ops/patch_mention_filter.py` + `tools/ops/recover_*.sh` | 4 类真实运行故障（mention 过滤丢弃/假派发/LLM 超时/空回合）全部根因分析+代码级根治+回归验证，见 [docs/RUN_ISSUES_AND_SOLUTIONS.md](docs/RUN_ISSUES_AND_SOLUTIONS.md) |

完整证据索引与复现步骤见 [docs/EVIDENCE.md](docs/EVIDENCE.md)。

## 后续替换点

| 当前内容 | 后续替换方向 | 迁移成本 |
| --- | --- | --- |
| HTTP mock 工具网关 | 真实 MCP Server 或 Higress MCP 代理 | 仅协议适配层（`mcp_server.py` 已实证 25 工具零业务重构） |
| `scenarios/*.json` | 真实 CRM、DMS、价格、金融审批、知识库数据源 | 数据源适配，工具接口不变 |
| 8 个业务 Worker 的内联 AgentSpec/Skill | Nacos AI Registry 中的 Prompt、Skill、AgentSpec、AgentTeam Spec | 注册发布，Spec 结构不变 |
| `skills/*/SKILL.md` 评审材料 | 发布到 Nacos AI Registry 或 AgentTeams Skill Registry，由 Worker 按版本/标签动态加载 | 版本化加载，Skill 契约不变 |
| TF-IDF RAG（纯 Python） | PolarDB for PostgreSQL + pgvector 向量库 | 替换 `TFIDFRagIndex.search` 为向量库查询，接口不变；**迁移 PoC 已完成**（三后端可插拔 + 等价性验证 + DDL/索引/权限/回滚方案，见 [docs/RAG_PGVECTOR_MIGRATION.md](docs/RAG_PGVECTOR_MIGRATION.md)） |
| Agent 记忆（JSONL + TF-IDF） | PolarDB 向量库 / 统一模型层长记忆 | 持久化替换，`recall_semantic` 接口不变 |
| 工具网关 Trace + 审计 JSONL | LoongSuite / AgentScope Studio / AgentLoop 全链路可观测 | 语义已对齐 OTel GenAI，`otel_exporter.py` 已实证真 OTel SDK 导出，采集器替换 |
| AgentTeams 真实 LLM 推理驱动 | 多模型路由 / 自部署模型 / 更强调度策略 | 编排契约与 trace 结构不变；**真框架已跑**（11 容器 v1.1.2 + Matrix + 2026-08-16 三场景全闭环，116 次工具调用 100% 成功）；三个 LLM 决策点已由百炼 LLM 自主驱动（`llm_client.py` + `llm_decision_demo.py`） |
| LLM 决策点（百炼 qwen-plus，三个） | qwen-max / 自部署模型 / 多模型路由 | `LLM_MODEL` 环境变量切换，prompt 与降级逻辑不变 |
| OSS 证据归档（真 REST + 本地降级） | MCP Server（oss_put/get/list tool）或阿里云 OSS SDK | OssObjectStore REST→MCP tool schema 适配，`store_type` 契约不变 |
| 短信审批告警（真 REST + 本地降级） | MCP Server（sms.approval.alert tool）或阿里云短信 SDK | AliyunSmsSender REST→MCP tool schema 适配，`channel_type` 契约不变 |

## 开源与合规

- 开源计划：demo 代码包（本仓库）以 Apache-2.0 协议开源（见根目录 LICENSE）；Skill 模板、MCP 接口契约（[docs/INTERFACE_CONTRACT.md](docs/INTERFACE_CONTRACT.md)）、场景数据集（脱敏）同步开放复用。
- 架构总览：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)（分层架构图 + AgentTeams 映射 + Skill/MCP/RAG/可观测/审计闭环）。
- 数据来源：场景数据为构造的演示数据，不包含真实客户个人信息；真实业务接入时需脱敏与授权。
- 依赖披露：AgentTeams（Agent 协同）、Python 标准库（mock 网关 + LLM 决策，零第三方依赖）、外部 LLM API（运行时配置）。
