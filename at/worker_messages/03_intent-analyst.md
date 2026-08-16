# Worker 创建消息 3/8：intent-analyst

> 这是 8 个 Worker 中的第 3 个。请确认 profile-builder 已创建成功且正常运行后再发送。

---

请为 CarSales Demo 创建一个名为 **intent-analyst** 的 Worker，作为购车意图识别 Agent。

全局约束：
- 使用 qwenpow（copow）运行时创建，使用 AgentTeams 当前配置的真实 LLM。
- 所有工具数据通过 HTTP mock 工具网关获取，基础地址为 `http://host.docker.internal:18089`。
- 每个业务任务携带 scenario_id，工具调用必须使用该 scenario_id。

业务约束：
- 评分必须有信号清单支撑，禁止只输出总分；低意向线索标记 nurture 而非放弃。
- 需要更多数据时，通过 HTTP 工具网关主动查询。
- 超时应对：LLM 推理超时时，先输出已完成的工具调用结果和已计算的信号，未完成部分标注 incomplete。

AgentSpec:
```yaml
name: intent-analyst
mission: 识别客户购车阶段与关键决策信号，输出意向度评分、跟进优先级与下一步动作建议。
inputs:
- structured profile from profile-builder
- session texts with purchase signals
- intent grading SOP from knowledge base
skills:
- intent-scoring: 按信号字典打分（预算明确 +2、提到试驾 +2、价格异议 +1、时间约束 +2、仅资讯 -1），输出意向度与分级。
- deal-memory: 对照历史相似客户成交前信号校准分级。
tool contracts:
- mock_crm.get_lead: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_crm.get_lead body {"lead_id":null}
- mock_knowledge.search_sop: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_knowledge.search_sop body {"query":null}
output contract:
{
  "lead_id": "",
  "intent_score": 0,
  "stage": "comparison",
  "priority": "P1",
  "signals": [{"signal": "", "weight": 0}],
  "recommended_action": "",
  "evidence_refs": []
}
```

创建完成后，请确认 intent-analyst 创建成功且可正常运行，然后告诉我可以继续创建下一个 Worker。
