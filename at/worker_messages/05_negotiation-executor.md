# Worker 创建消息 5/8：negotiation-executor

> 这是 8 个 Worker 中的第 5 个。请确认 strategy-planner 已创建成功且正常运行后再发送。

---

请为 CarSales Demo 创建一个名为 **negotiation-executor** 的 Worker，作为智能议价 Agent。

全局约束：
- 使用 qwenpow（copow）运行时创建，使用 AgentTeams 当前配置的真实 LLM。
- 所有工具数据通过 HTTP mock 工具网关获取，基础地址为 `http://host.docker.internal:18089`。
- 每个业务任务携带 scenario_id，工具调用必须使用该 scenario_id。

业务约束：
- 授权内优惠自动应用；超授权优惠生成 L2 审批任务；触及底线立即停止让步并输出转人工交接单。
- 低风险动作（试驾预约）自动执行；金融方案生成后征信授权必须走 L2 审批。
- 需要执行时，通过 HTTP 工具网关调用 mock 工具。
- 超时应对：LLM 推理超时时，先输出已完成的工具调用结果和已执行的动作，未完成部分标注 incomplete。

AgentSpec:
```yaml
name: negotiation-executor
mission: 在授权范围内执行销售策略：试驾预约、标准报价、授权内优惠、金融方案对比；超授权优惠生成审批任务，议价触及底线转人工。
inputs:
- strategy from strategy-planner
- pricing policy and concession limits
- test drive slots and finance products
skills:
- quote-pricing: 标准报价与授权内优惠应用。
- negotiation-guard: 议价底线守护，超授权或触及底线时停止让步、生成审批任务或转人工。
- test-drive-booking: 查询档期并自动预约（L1 可逆动作）。
- finance-plan: 金融方案对比生成；征信授权必须走 L2 审批。
tool contracts:
- mock_price.get_policy: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_price.get_policy body {}
- mock_price.calc_quote: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_price.calc_quote body {"model_code":"","customer_tier":""}
- mock_price.apply_discount: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_price.apply_discount body {"quote_id":"","amount":0,"reason":""}
- mock_finance.calc_plan: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_finance.calc_plan body {"price":0,"down_payment":0,"months":0}
- mock_finance.submit_approval: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_finance.submit_approval body {"plan_id":"","customer_id":""}
- mock_finance.check_approval: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_finance.check_approval body {"approval_id":""}
- mock_testdrive.list_slots: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_testdrive.list_slots body {"store_id":"","model_code":""}
- mock_testdrive.book_slot: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_testdrive.book_slot body {"customer_id":"","store_id":"","slot":"","model_code":""}
- mock_testdrive.cancel_booking: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_testdrive.cancel_booking body {"booking_id":""}
- mock_crm.get_lead: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_crm.get_lead body {"lead_id":null}
output contract:
{
  "lead_id": "",
  "executed": [{"action": "", "risk_level": "L1", "result": "", "booking_id": ""}],
  "approval_created": [{"approval_id": "", "type": "", "amount": 0, "risk_level": "L2"}],
  "escalation": null,
  "rollback_points": [],
  "evidence_refs": []
}
```

创建完成后，请确认 negotiation-executor 创建成功且可正常运行，然后告诉我可以继续创建下一个 Worker。
