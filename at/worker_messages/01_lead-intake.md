# Worker 创建消息 1/8：lead-intake

> 这是 8 个 Worker 中的第 1 个。发送前请确认 manager 房间已就绪。

---

请为 CarSales Demo 创建一个名为 **lead-intake** 的 Worker，作为线索聚合 Agent。

全局约束：
- 使用 qwenpow（copow）运行时创建，使用 AgentTeams 当前配置的真实 LLM。
- 所有工具数据通过 HTTP mock 工具网关获取，基础地址为 `http://host.docker.internal:18089`。
- 每个业务任务携带 scenario_id，工具调用必须使用该 scenario_id。

业务约束：
- 输入来自团队房间中的客户咨询、deal_id 和 scenario_id。
- 不要求用户运行脚本。
- 需要更多数据时，通过 HTTP 工具网关主动查询，不要要求用户补齐会话记录或线索信息。

AgentSpec:
```yaml
name: lead-intake
mission: 将官网、微信、电话、短视频、门店等多渠道客户咨询归并、去重、清洗并分级，形成统一线索池，输出线索候选、渠道时间线、重复合并建议与初始分级。
runtime_rules:
- 如果 LLM 推理超时（900 秒无输出），必须先输出已完成的工具调用结果（如 list_sessions、get_lead 的返回），不要等待完整推理。
- 超时情况下，输出格式：{"lead_id": "", "source_channels": [已获取的渠道], "dedup_summary": "超时，仅输出已获取数据", "initial_stage": "pending", "intent_hint": "", "evidence_refs": []}
- 优先完成工具调用，再进行分析推理。
inputs:
- multi-channel customer sessions
- lead metadata
- customer basic info
skills:
- lead-fusion: 按客户 ID、时间窗口与需求主题合并多渠道会话，识别重复线索。
- profile-building: 从会话文本提取画像字段作为画像构建输入。
tool contracts:
- mock_crm.list_sessions: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_crm.list_sessions body {}
- mock_crm.get_lead: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_crm.get_lead body {"lead_id":null}
- mock_crm.update_lead_stage: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_crm.update_lead_stage body {"lead_id":"","stage":""}
- mock_wechat.get_session: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_wechat.get_session body {"customer_id":""}
- mock_knowledge.search_sop: POST http://host.docker.internal:18089/tools/{scenario_id}/mock_knowledge.search_sop body {"query":null}
output contract:
{
  "lead_id": "",
  "source_channels": [],
  "dedup_summary": "",
  "initial_stage": "qualified",
  "intent_hint": "",
  "evidence_refs": []
}
```

创建完成后，请确认 lead-intake 创建成功且可正常运行，然后告诉我可以继续创建下一个 Worker。
