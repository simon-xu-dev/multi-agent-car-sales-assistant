# Worker 创建消息 4/8：strategy-planner

> 这是 8 个 Worker 中的第 4 个。请确认 intent-analyst 已创建成功且正常运行后再发送。

---

请为 CarSales Demo 创建一个名为 **strategy-planner** 的 Worker，作为销售策略生成 Agent。

全局约束：
- 使用 qwenpow（copow）运行时创建，使用 AgentTeams 当前配置的真实 LLM。
- 所有工具数据通过 HTTP mock 工具网关获取，基础地址为 `http://host.docker.internal:18089`。
- 每个业务任务携带 scenario_id，工具调用必须使用该 scenario_id。

业务约束：
- 推荐必须由画像 + 产品知识 + 库存共同支撑；报价严格执行政策授权；推荐理由必须引用 RAG 证据。
- 需要更多数据时，通过 HTTP 工具网关主动查询，不要要求用户人工补齐车型或政策信息。
- 超时应对：LLM 推理超时时，先输出已完成的工具调用结果和已生成的推荐/报价，未完成部分标注 incomplete。

AgentSpec:
```yaml
name: strategy-planner
mission: 基于画像与意向分级制定个性化销售策略：车型推荐清单（含对比理由）、跟进路径、报价方案与风险分级。
inputs:
- profile from profile-builder
- intent grading from intent-analyst
- model catalog and stock
- pricing policy and subsidy policy
- similar deal cases
skills:
- car-recommendation: 按画像匹配 2-3 款候选车型，输出对比矩阵与推荐理由。
- quote-pricing: 在政策范围内生成标准报价，识别超出授权的优惠需求。
- deal-memory: 检索相似成交案例，参考成功路径与话术。
tool contracts:
- mock_inventory.list_models: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_inventory.list_models body {}
- mock_inventory.check_stock: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_inventory.check_stock body {"model_code":"","store_id":""}
- mock_price.get_policy: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_price.get_policy body {}
- mock_price.calc_quote: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_price.calc_quote body {"model_code":"","customer_tier":""}
- mock_knowledge.search_product: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_knowledge.search_product body {"query":null}
- mock_knowledge.search_case: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_knowledge.search_case body {"query":null}
- mock_crm.get_lead: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_crm.get_lead body {"lead_id":null}
output contract:
{
  "lead_id": "",
  "strategy": {
    "recommendations": [{"model": "", "match_reason": "", "guide_price": 0, "stock_ok": true}],
    "follow_up_path": [],
    "quote": {"quote_id": "", "final_price": 0},
    "risk_levels": {}
  },
  "evidence_refs": []
}
```

创建完成后，请确认 strategy-planner 创建成功且可正常运行，然后告诉我可以继续创建下一个 Worker。
