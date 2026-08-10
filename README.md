# CarSales：基于多 Agent 的汽车销售自主成交智能助手（AgentTeams 最小可运行 Demo）

面向 GOAI「新智基座 | Agent Infra」赛题方向二（智能客服自主闭环）的汽车销售场景落地。用户只提供客户咨询与少量线索信息，AgentTeams 中的 8 个业务 LLM Agent 通过 HTTP mock 工具网关主动查询 CRM、库存、报价、金融、试驾、订单、知识库（RAG）与企业微信数据；创建 Team 时由 manager 创建独立 TeamLeader Worker `carsales-demo-leader` 负责调度协作，完成「线索获取 — 需求分析 — 成交促进 — 售后运营 — 知识沉淀」的零人工销售闭环。

完整运行手册见 [at/AGENTTEAMS_RUNBOOK.md](at/AGENTTEAMS_RUNBOOK.md)。

## Demo 要证明什么

1. AgentTeams 可以创建并管理 8 个职责明确的业务 LLM Agent，并在创建 Team 时生成 1 个独立 TeamLeader Worker。
2. Worker 在 Docker 中也能通过 HTTP 工具网关主动取证，不依赖宿主机目录。
3. 三个销售场景分三次独立处理，展示完整成交闭环、金融审批闭环与老客户运营闭环。
4. 低风险动作（试驾预约、标准报价、模板消息）进入自动化执行语义；高风险动作（超授权优惠、征信授权、订单确认）只生成审批计划；议价触及底线停止让步并转人工。
5. 全链路工具调用可观测：每次调用写入 Trace，支持回放与审计。

## Demo 场景

| 场景 ID | 场景 | 预期处置 |
| --- | --- | --- |
| `family_suv_deal` | 二胎家庭 SUV 购车，多渠道线索（官网+企微+电话） | 归并线索、构建画像、推荐车型、自动预约试驾、标准报价、超授权优惠生成 L2 审批、订单草稿、案例沉淀 |
| `first_car_finance` | 首购客户金融方案（短视频渠道） | 画像与意图识别、金融方案对比、征信授权生成 L2 审批、订单草稿（审批前不确认） |
| `trade_in_renewal` | 老客户置换 + 售后运营 | 历史画像 RAG 召回、置换方案测算、议价触及底线转人工、售后权益模板触达、复购沉淀 |

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

```text
carsales-demo/
├── agents/            # 8 个业务 Agent 定义（评审材料，附录 A 模板）
├── skills/            # 11 个可复用 Skill（评审材料，附录 B 模板）
├── tools/             # HTTP mock 工具网关（8 个企业系统 + 验证探针）
│   ├── mock_tools.py
│   ├── mock_tool_server.py
│   ├── tool_catalog.json     # 工具目录与 MCP 未来映射
│   └── MCP_MAPPING.md        # 等价 MCP 集成契约
├── scenarios/         # 3 个销售场景数据（含预期结果）
├── at/                # AgentTeams 编排层
│   ├── create_agents_messages.md   # 8 Worker + Team 完整创建消息
│   ├── team_spec.json              # Team 拓扑与工作流
│   ├── run_demo_task_message.md    # 3 个销售任务消息
│   ├── AGENTTEAMS_RUNBOOK.md       # 运行手册
│   ├── agentteams.env.example
│   ├── nacos_registry_mock.json    # AI 资源治理 mock
│   └── AgentTeam.md                # Team 形态说明
└── docs/              # 评审与演进文档
```

## 最短运行流程

1. 启动 mock 工具网关：

```bash
cd <DEMO_DIR>
python3 tools/mock_tool_server.py --host 0.0.0.0 --port 18089
```

2. 安装 AgentTeams，并按安装器引导完成 LLM/API Key/端口/运行时配置：

```bash
bash <(curl -sSL https://higress.ai/hiclaw/install.sh)
```

3. 找到 Docker 容器访问工具网关的地址：

```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{println .Gateway}}{{end}}' hiclaw-manager
docker exec -it hiclaw-manager curl http://<GATEWAY_IP>:18089/health
```

如果 manager 容器名不是 `hiclaw-manager`，按运行手册第 4 步先确认实际容器名。

4. 在 Element Web 打开 `manager` 房间，把 [at/create_agents_messages.md](at/create_agents_messages.md) 里的 `<MOCK_TOOL_BASE_URL>` 替换成 `http://<GATEWAY_IP>:18089` 后，将完整创建请求复制给 `manager`。创建请求已要求所有 Worker 使用 `qwenpow`（`copow`/`QwenPaw`）运行时，并由 `manager` 严格串行创建 8 个业务 Worker；创建 Team 时再生成独立 TeamLeader Worker `carsales-demo-leader`。

5. 在 Element Web/Matrix 会话列表中找到名称以 `Team` 开头、对应 `carsales-demo` 的 Team 房间。进入房间后，在输入框先 `@<team_leader_name>` 选中带 leader 名字的成员，再把 [at/run_demo_task_message.md](at/run_demo_task_message.md) 中的第一个销售任务复制到这条 @ 消息里发送；等报告输出完成后，再用同样方式发送下一条。销售任务不要发给 `manager`。

6. 查看运行证据：

```bash
curl http://127.0.0.1:18089/tools/family_suv_deal/tools/trace
```

## 后续替换点

| 当前内容 | 后续替换方向 |
| --- | --- |
| HTTP mock 工具网关 | 真实 MCP Server 或 Higress MCP 代理 |
| `scenarios/*.json` | 真实 CRM、DMS、价格、金融审批、知识库数据源 |
| 8 个业务 Worker 的内联 AgentSpec/Skill | Nacos AI Registry 中的 Prompt、Skill、AgentSpec、AgentTeam Spec |
| `skills/*/SKILL.md` 评审材料 | 发布到 Nacos AI Registry 或 AgentTeams Skill Registry，由 Worker 按版本/标签动态加载 |
| mock 知识库检索 | PolarDB for PostgreSQL + pgvector 向量库实现 RAG |
| 工具网关 Trace | LoongSuite / AgentScope Studio / AgentLoop 全链路可观测与评估 |

## 开源与合规

- 开源计划：demo 代码包（本仓库）以 Apache-2.0 协议开源（见根目录 LICENSE）；Skill 模板、MCP 接口契约、场景数据集（脱敏）同步开放复用。
- 数据来源：场景数据为构造的演示数据，不包含真实客户个人信息；真实业务接入时需脱敏与授权。
- 依赖披露：AgentTeams（Agent 协同）、Python 标准库（mock 网关）、外部 LLM API（运行时配置）。
