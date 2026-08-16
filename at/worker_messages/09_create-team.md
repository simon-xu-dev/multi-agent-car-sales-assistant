# Team 创建消息（8 个 Worker 全部就绪后发送）

> 请确认以下 8 个业务 Worker 都已创建成功且正常运行后再发送：
> 1. lead-intake  2. profile-builder  3. intent-analyst  4. strategy-planner
> 5. negotiation-executor  6. order-executor  7. customer-ops  8. knowledge-miner

---

请创建一个名为 **carsales-demo** 的 Team，包含以下 8 个业务 Worker：
1. lead-intake
2. profile-builder
3. intent-analyst
4. strategy-planner
5. negotiation-executor
6. order-executor
7. customer-ops
8. knowledge-miner

Team 创建要求：
- 创建 Team 时，必须创建一个新的独立 Worker 作为 TeamLeader，名称必须是 **carsales-demo-leader**。
- 禁止把 8 个业务 Worker 中的任何一个直接指定为 leader。
- 8 个业务 Worker 只作为被 TeamLeader 调度的专业角色参与 Team。

请同时创建或确认该 Team 对应的 Matrix Team 房间，并在创建完成后告诉我：
1. 房间名称或入口
2. 需要 @ 的 team_leader_name（应为 carsales-demo-leader）

团队运行规则：
- 使用 AgentTeams 当前配置的真实 LLM 完成推理和协作。
- 所有工具数据通过 HTTP mock 工具网关获取，基础地址为 `http://host.docker.internal:18089`。
- 收到销售任务后，由 TeamLeader 按 deal_type 路由调度（按需调用，不需要 8 个全部参与）：
  - **new_deal**（DEAL-2001 全链路成交）：lead-intake → profile-builder → intent-analyst → strategy-planner → negotiation-executor → order-executor（check_deal）→ 异步扇出 customer-ops + knowledge-miner → 汇总报告。
  - **finance**（DEAL-2002 首购金融）：跳过 lead-intake，profile-builder → intent-analyst → strategy-planner → negotiation-executor（金融方案 + 征信 L2 审批）→ order-executor（check_deal）→ 异步 knowledge-miner → 汇总报告。
  - **trade_in**（DEAL-2003 老客户置换）：跳过 lead-intake，profile-builder（记忆召回）→ strategy-planner（置换方案）→ negotiation-executor（议价底线/转人工）→ order-executor（check_deal）→ 异步 customer-ops + knowledge-miner → 汇总报告。
  - **complaint**（投诉/价格异议）：不进主链，直接转人工并输出交接单。
- 主链串行推进，各步骤的中间结论（画像、策略、执行结果）必须随消息传给下一个 Worker，禁止跳步、并行争抢同一工具或跳过 check_deal 直接写报告。
- 不要让用户运行 demo 脚本；用户只会给出客户咨询、deal_id、scenario_id 和 deal_type（线索标签）。
- 每次只处理一个销售任务；处理完成后输出一份销售闭环报告。
- 销售闭环报告必须包含：线索与画像、推荐与报价、执行动作（低风险自动/高风险审批）、审批项、转人工项、订单状态、案例沉淀结果。

门店枚举映射：任务文本中的门店名对应标准 store_id（杭州滨江旗舰店/滨江店/HZ-BINJIANG → store_001；上海虹桥店/虹桥店 → store_002；广州天河店/天河店 → store_003）。Worker 调用 check_stock / list_slots / book_slot / reserve_car 时必须传入标准 store_id。

全部创建完成后，请输出创建结果摘要，至少包含：
- 8 个业务 Worker 的创建状态和运行时类型。
- Team 创建时生成的独立 TeamLeader Worker 名称和运行时类型，必须单独列出 carsales-demo-leader。
- carsales-demo Team 的创建状态。
- TeamLeader 指定结果，必须显示 carsales-demo-leader 是 TeamLeader。
- Matrix 会话列表中名称以 Team 开头、对应 carsales-demo 的 Team 房间名称或入口。
- 需要在 Team 房间中 @ 的 team_leader_name，并说明它对应 carsales-demo-leader。
- 提醒用户后续销售任务必须进入 Team 房间后，通过 @\<team_leader_name\> 的消息发送，不要发送给 manager。
