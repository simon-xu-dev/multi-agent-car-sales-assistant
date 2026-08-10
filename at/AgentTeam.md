# CarSales Demo AgentTeam

这个文件描述 demo 使用的 Team 形态。主运行路径是 AgentTeams + 真实 LLM Worker + HTTP mock 工具网关。

## AgentTeams 运行时映射

| AgentTeams 概念 | Demo 设计 |
| --- | --- |
| Manager 房间 | 接收自包含的 Agent 创建消息 |
| Team 房间 | Matrix 会话列表中名称以 `Team` 开头；用户通过 `@<team_leader_name>` 发送销售任务 |
| TeamLeader Worker | 创建 Team 时由 manager 生成的独立 Worker `carsales-demo-leader` |
| Worker 房间 | 运行 8 个角色明确的业务 LLM Agent |
| Worker 运行时 | 统一使用 `qwenpow`（`copow`/`QwenPaw`） |
| 创建策略 | `manager` 串行创建 8 个业务 Worker；创建 Team 时再生成独立 TeamLeader Worker `carsales-demo-leader`；禁止把业务 Worker 指定为 leader |
| AgentSpec | 8 个业务 Worker 内联在 `at/create_agents_messages.md` |
| 任务输入 | `at/run_demo_task_message.md` 中的客户咨询与 deal_id/scenario_id |
| 工具调用 | HTTP mock 工具网关（8 个企业系统 mock + 验证探针） |
| 风险分级 | L0/L1 自动执行；L2/L3 仅生成审批计划；议价触及底线转人工 |
| Skill Registry | 当前运行时使用创建消息中的内联 Skill 语义；`skills/*/SKILL.md` 和 `at/nacos_registry_mock.json` 用于评审和后续替换 |

AgentTeams 组件经常运行在 Docker 中，因此运行时不依赖宿主机上的项目目录路径。Worker 通过 HTTP 地址访问工具网关，并根据 `scenario_id` 查询对应销售场景数据。当前 demo 不要求 Worker 读取宿主机上的 `skills/*/SKILL.md`；后续可把这些 Skill 发布到 Nacos AI Registry 或 AgentTeams Skill Registry，再由 Worker 按版本/标签动态加载。

## 工作流

1. TeamLeader `carsales-demo-leader` 接收 Team 房间中的销售任务，提取 `deal_id`、`scenario_id` 与客户咨询，按需调度业务 Worker。
2. `Lead Intake Agent` 归并多渠道会话、去重分级，输出统一线索。
3. `Profile Builder Agent` 构建客户画像（预算、家庭、场景、偏好）并标注置信度。
4. `Intent Analyst Agent` 识别购车阶段与意向评分，确定跟进优先级。
5. `Strategy Planner Agent` 输出车型推荐、报价与跟进路径（RAG 证据支撑）。
6. `Negotiation Executor Agent` 自动执行试驾预约/标准报价/授权内优惠；超授权优惠生成 L2 审批任务；议价触及底线输出转人工交接单。
7. `Order Executor Agent` 幂等创建订单草稿、跟踪状态、回滚与成交验证。
8. `Customer Ops Agent`（按需）执行售后触达与复购运营。
9. `Knowledge Miner Agent` 复盘并脱敏沉淀成交案例，输出 Skill 更新建议；TeamLeader 汇总最终销售闭环报告。

## Demo 场景

| 场景 | 客户类型 | 闭环路径 | 安全策略 |
| --- | --- | --- | --- |
| `family_suv_deal` | 二胎家庭 SUV 购车 | 线索 -> 画像 -> 推荐 -> 试驾 -> 报价 -> 优惠审批 -> 订单草稿 -> 案例沉淀 | 试驾预约/标准报价 L1 自动；超 1% 优惠 L2 审批；订单 L2 草稿 |
| `first_car_finance` | 首购金融方案 | 线索 -> 画像 -> 金融方案 -> 征信审批 -> 订单草稿 | 方案计算 L1；征信授权 L2 审批；审批前订单仅草稿 |
| `trade_in_renewal` | 老客户置换 + 售后 | 历史画像 -> 置换方案 -> 议价 -> 转人工 -> 售后触达 -> 复购沉淀 | 历史画像 L0 RAG；3 万额外优惠超授权且触底线 -> 停止让步转人工；模板触达 L1 |

## RAG 能力覆盖（赛题要求 4 项中实现 2 项以上，本方案实现 4 项）

| 赛题 RAG 能力 | 本方案实现 |
| --- | --- |
| 1. Agent 记忆存储 | `mock_crm.get_customer_history` 客户历史记忆 + `deal-memory` Skill（时间窗口查询 + 语义检索） |
| 2. 知识库 RAG | `mock_knowledge.search_product/search_sop/search_case`（产品知识 / SOP / 历史案例 / 政策） |
| 3. 共享状态管理 | `mock_crm.update_lead_stage` 线索状态机 + Team 上下文传递（并发一致性由 TeamLeader 串行调度保证） |
| 4. 轨迹可观测 | 工具网关 Trace（时间/工具/参数/结果）+ actions 审计 + 可观测设计（AgentLoop） |
