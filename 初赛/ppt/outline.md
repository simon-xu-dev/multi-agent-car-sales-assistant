# 初赛方案 PPT 大纲（已确认）

- 项目：基于多 Agent 的汽车销售自主成交智能助手
- 风格：清爽专业风（浅色背景、专业蓝 #2563EB + 青色 #0F766E 强调、结构化卡片/流程布局）
- 比例：16:9，共 13 页，无需外部图片素材（图形均由脚本绘制）
- 生成方式：python-pptx 可编辑 PPT（路径 2）

## Slide 1：封面（cover）
- 项目名称：基于多 Agent 的汽车销售自主成交智能助手
- 副标题：覆盖"线索获取—需求分析—成交促进—售后运营—知识沉淀"的自主销售闭环
- 关键词标签：Multi-Agent / Skill / MCP / RAG / 可观测

## Slide 2：行业痛点（problem）
- 线索分散难统一：官网/微信/电话/短视频/门店多渠道，线索无法统一管理
- 客户画像靠人工：需求识别依赖个人经验，判断慢、口径不一
- 销售流程割裂：推荐/报价/试驾/金融各自为政
- 优秀经验难沉淀：成功案例与话术无法复用传承
- 结论条：线索流失率高 · 成交周期长 · 销售效率低

## Slide 3：总体方案（architecture）
- 五段闭环：线索获取 → 需求分析 → 成交促进 → 售后运营 → 知识沉淀（经验回流）
- 五大技术支柱：Multi-Agent 协同决策 / Skill 能力抽象 / MCP 工具连接 / RAG 知识增强 / 可观测持续优化

## Slide 4：多 Agent 分工（concept）
- 8 大职能 Agent：线索聚合、客户画像、购车意图识别、销售策略生成、智能议价、订单执行、客户运营、知识沉淀
- 编排基点：AgentTeams 分层架构 Manager → TeamLeader → Worker；TeamLeader（salesflow-demo-leader）在 Team 房间拆解调度，Human-in-the-loop 随时介入

## Slide 5：端到端自主闭环（process）
- 任务输入 → 任务拆解 → 上下文传递与工具调用 → 结果验证 → 审批与回滚（高风险动作人工确认）→ 证据与经验沉淀
- 闭环与 AgentTeams 对应：任务输入=Team 房间任务消息；拆解=TeamLeader 调度；上下文=Matrix Room 事件流；状态=Event/Status + Nacos 状态回写

## Slide 6：AgentTeams 协同设计基点：框架能力映射（table）
- 六维映射表：角色编排 / 任务拆解 / 上下文传递 / 协同执行 / 状态追踪 / 人机协同
- 对应框架能力：create_agent/create_team 分层、TeamLeader 指令分解、Matrix Room + TeamHarness、Worker 运行时 QwenPaw + 工具网关、Event/Status + Nacos（Desired→Applied→Status）、Human-in-the-loop 审批与回滚

## Slide 7：Skill 体系（list/table）
- 11 个可复用 Skill：lead-fusion / profile-building / intent-scoring / car-recommendation / quote-pricing / negotiation-guard / test-drive-booking / finance-plan / order-safe-execute / case-mining / deal-memory
- 每行说明能力、用途、输入/输出、失败处理；10 字段模板（含调用条件/依赖工具/权限安全/复用价值）；Nacos 版本化与灰度发布

## Slide 8：MCP 工具集成（diagram）
- Agent/Skill 能力抽象层 → Higress AI 网关 + MCP 协议层（统一入口/鉴权/路由/限流/Schema/审计/重试/幂等）→ CRM、库存(DMS)、金融审批、保险、合同、企业微信
- 契约标准化：工具.函数 命名空间 + future_mcp_mapping，迁移 MCP Server 仅协议适配

## Slide 9：RAG 知识增强（concept）
- 四类知识源：产品知识、销售 SOP、历史成交案例、补贴与政策
- 机制：MCP 接数据源 → Skill 封装检索与证据对齐 → Agent 判断证据充分性；无证据不编造
- 覆盖 RAG 4 项能力中 2 项：Agent 记忆存储 + 知识库 RAG（PolarDB 承载）

## Slide 10：全链路可观测（metrics）
- 观测对象：Agent 推理轨迹、Skill 调用、MCP 工具执行、RAG 检索
- 数据类型（OTel GenAI 语义）：Trace（Agent/Skill/MCP/RAG/LLM Span）、Log（决策依据/失败/权限/审批，TraceId 关联）、Metrics（会话/时延/Token/工具成功率）
- 应用：在线监控告警、LLM-as-Judge 离线评估、回流 Dataset 迭代
- 落地：LoongSuite + AgentScope Studio（开源）→ AgentLoop（生产）

## Slide 11：推荐工具链：全链路治理架构（toolchain）
- Nacos AI Registry：Agent/Skill/Prompt/MCP 注册、灰度、回滚、审计
- Higress AI 网关：统一入口、鉴权、路由、限流、观测
- PolarDB 数据层：向量/长记忆/RAG/审计存储
- RocketMQ：审批事件/订单状态流转/触达任务，可靠投递 + 幂等
- 阿里云官方用云 Skills：承载基础云能力（模型/短信/证据归档），鉴权走 Higress
- 工具观：必要性、接口契约、可替换性、权限边界、迁移成本

## Slide 12：创新点与开放复用价值（comparison）
- 对比：传统智能客服（回答问题）vs 本方案（自主推进成交）
- 复用：Skill 独立复用、MCP 标准接口、可迁移房地产/保险/金融/高端零售、开源计划

## Slide 13：当前进展与路线图（timeline）
- 已完成：Agent Identity 清单（8 字段模板）、Skill 清单 11 项（10 字段模板）、AgentTeams 可运行代码包、自检 36/36 通过
- 下一阶段：企业系统对接（CRM/库存/金融审批）、生产级 Skill 工程、可观测部署、真实场景验证
- 长期：自主成交能力持续提升、量化评估与策略自进化、行业复制与开源生态
- 结语：让 AI 不止于回答，而是自主推进每一次成交
