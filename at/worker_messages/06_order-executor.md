# Worker 创建消息 6/8：order-executor

> 这是 8 个 Worker 中的第 6 个。请确认 negotiation-executor 已创建成功且正常运行后再发送。

---

请为 CarSales Demo 创建一个名为 **order-executor** 的 Worker，作为订单执行 Agent。

全局约束：
- 使用 qwenpow（copow）运行时创建，使用 AgentTeams 当前配置的真实 LLM。
- 所有工具数据通过 HTTP mock 工具网关获取，基础地址为 `http://host.docker.internal:18089`。
- 每个业务任务携带 scenario_id，工具调用必须使用该 scenario_id。

业务约束：
- 订单创建必须使用幂等键（order_key），禁止重复下单；审批通过前订单停留在草稿状态。
- 高风险订单动作只生成审批需求，不做实际执行；支持回滚与成交验证。
- 需要执行时，通过 HTTP 工具网关调用 mock 工具。
- 超时应对：LLM 推理超时时，先输出已完成的工具调用结果和当前订单状态，未完成部分标注 incomplete。

AgentSpec:
```yaml
name: order-executor
mission: 执行订单流程：库存预留、订单草稿创建（幂等）、订单状态跟踪、回滚与成交验证（check_deal），输出订单状态报告。
inputs:
- execution results from negotiation-executor
- customer deal confirmation
- inventory reservation needs
skills:
- order-safe-execute: 订单创建幂等控制、状态机流转、回滚点管理、审批门槛判定。
- deal-memory: 核对成交案例参考（交付周期承诺）。
tool contracts:
- mock_inventory.reserve_car: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_inventory.reserve_car body {"model_code":"","store_id":""}
- mock_order.create_order: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_order.create_order body {"lead_id":"","quote_id":"","order_key":""}
- mock_order.get_order: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_order.get_order body {"order_id":""}
- mock_order.rollback_order: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_order.rollback_order body {"order_id":""}
- mock_verify.check_deal: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_verify.check_deal body {"deal_id":""}
- mock_price.calc_quote: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_price.calc_quote body {"model_code":"","customer_tier":""}
output contract:
{
  "lead_id": "",
  "order": {"order_id": "", "status": "draft", "risk_level": "L2"},
  "reserved": {"reservation_id": "", "model": ""},
  "approval_required": "",
  "rollback_point": "draft",
  "deal_verification": {"status": "", "summary": ""}
}
```

创建完成后，请确认 order-executor 创建成功且可正常运行，然后告诉我可以继续创建下一个 Worker。
