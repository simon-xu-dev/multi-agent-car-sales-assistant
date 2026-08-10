# MCP Mapping Notes（工具集成契约）

SalesFlow 初赛 demo 使用 HTTP mock tool gateway，让 AgentTeams 中的 Docker Worker 可以通过网络访问 mock CRM、库存、报价、金融、试驾、订单、知识库（RAG）和企业微信工具。

当前工具网关不是 MCP Server，但每个 HTTP 工具都有明确的未来 MCP 映射。后续只需要把 HTTP endpoint 替换为真实 MCP Server 或 Higress MCP 代理，Agent 的 Prompt / Skill / 工具契约可以保持稳定，不需要重新设计工具调用链。

## HTTP 调用协议

```text
POST http://<MOCK_TOOL_BASE_URL>/tools/{scenario_id}/{tool_name}.{function_name}
Content-Type: application/json
```

示例：

```bash
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/mock_crm.list_sessions \
  -H 'Content-Type: application/json' \
  -d '{}'
```

## 工具映射

| HTTP mock tool | Demo function | Future MCP tool | 对应企业系统 |
| --- | --- | --- | --- |
| `mock_crm` | `get_lead`, `list_sessions`, `get_customer_history`, `update_lead_stage` | `crm.lead.query`, `crm.lead.stage_update` | CRM / 线索管理 |
| `mock_inventory` | `list_models`, `check_stock`, `reserve_car` | `dms.inventory.query`, `dms.inventory.reserve` | 库存 / DMS |
| `mock_price` | `get_policy`, `calc_quote`, `apply_discount` | `pricing.policy.query`, `pricing.quote.calc`, `pricing.discount.apply` | 价格与优惠系统 |
| `mock_finance` | `calc_plan`, `submit_approval`, `check_approval` | `finance.plan.calc`, `finance.approval.submit`, `finance.approval.query` | 金融审批系统 |
| `mock_testdrive` | `list_slots`, `book_slot`, `cancel_booking` | `testdrive.slot.query`, `testdrive.slot.book`, `testdrive.slot.cancel` | 试驾预约系统 |
| `mock_order` | `create_order`, `get_order`, `rollback_order` | `order.create`, `order.query`, `order.rollback` | 订单 / 合同系统 |
| `mock_knowledge` | `search_product`, `search_sop`, `search_case`, `save_case` | `knowledge.rag.search`, `knowledge.case.save` | 知识库 / RAG 向量库 |
| `mock_wechat` | `get_session`, `send_template_message` | `wechat.session.query`, `wechat.template_message.send` | 企业微信 SCRM |
| `mock_verify` | `check_deal` | `deal.verify` | 成交闭环验证探针 |

## 鉴权与审计契约（等价 MCP 契约）

- **协议**：HTTP JSON（未来迁移 MCP 仅需协议适配层）。
- **鉴权方式**：网关层面注入租户 / 门店上下文；生产环境由 Higress 统一鉴权与限流。
- **输入输出 Schema**：见 `tools/tool_catalog.json` 与各 Agent 的 Output Contract。
- **错误处理**：未知工具 / 未知场景返回 `{"ok": false, "error": ...}`，Agent 需按 Skill 的失败处理策略降级，禁止编造数据。
- **审计记录**：每次调用写入 `GET /tools/{scenario_id}/tools/trace` 的 Trace 记录（时间 / 工具 / 参数 / 结果预览），支撑全链路回放。
- **幂等控制**：`mock_order.create_order` 以 `order_key` 保证幂等；重复调用返回已有订单。
- **回滚能力**：`mock_testdrive.cancel_booking`、`mock_order.rollback_order` 提供低风险回滚点。
- **降级方式**：工具不可用时 Agent 输出证据缺口与人工建议，不猜测数据。

## 风险分级（贯穿所有工具）

| 等级 | 语义 | 示例 |
| --- | --- | --- |
| L0 | 只读查询 / 检索 | 查线索、查库存、RAG 检索、查订单 |
| L1 | 低风险自动执行（可逆） | 试驾预约、库存预留、标准报价、模板消息 |
| L2 | 审批后执行 | 超授权优惠、订单创建、征信授权 |
| L3 | 仅生成方案 / 人工执行 | 合同条款变更、大额特殊订单 |
