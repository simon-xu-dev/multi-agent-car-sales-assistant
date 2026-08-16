# 开放接口契约（等价 MCP 集成契约）

> 面向评审：本文件是 SalesFlow 工具能力的**稳定调用契约**。赛题要求"即使暂不采用 MCP，也需把外部工具抽象成可被 Agent / Skill 稳定调用的工具能力，说明工具名称、调用入口、参数 Schema、返回结构、权限范围、失败重试、幂等控制、审计日志和降级方式"。本契约覆盖全部 11 类工具（25 个函数，含 2 个官方用云 Skill 封装：OSS 证据归档 / 阿里云短信审批告警），并给出后续迁移到 MCP 的成本判断：**仅需协议适配层，业务 Skill 与 Agent 零改动**（`tools/mcp_server.py` 已实证）。

## 1. 协议

- **当前**：HTTP REST，`POST /tools/{scenario_id}/{tool_name}.{function_name}`，JSON 请求/响应，`{"ok": true, "result": ...}` 统一包装。
- **调用模式**：`call_pattern` 见 `tools/tool_catalog.json`（机器可读目录）。
- **MCP 等价**：FastMCP stdio Server（`tools/mcp_server.py`，25 工具），`_STATE_CACHE` 保持 quote/order/approval/assessment 跨调用状态，业务逻辑零重构。
- **迁移到 MCP 的成本**：工具调用链已按"工具名.函数名"命名空间组织，`future_mcp_mapping` 已预置（如 `crm.lead.query`、`pricing.discount.apply`、`order.confirm`、`finance.approval.approve`、`deal.audit.query`）；迁移到 MCP Server **仅需协议适配层替换 HTTP 适配器，业务 Skill 与 Agent 零改动**。`mcp_client_test.py` 12/12 断言已验证 initialize / tools/list / tools/call 全链路。

## 2. 鉴权方式

- **网关层**：注入租户/门店上下文（`scenario_id` 隔离每单状态）。
- **生产环境**：由 Higress AI 网关统一鉴权、限流、路由；STS 临时凭证访问 OSS（最小权限）。
- **审批权限**：`approve`/`reject` 需门店经理角色（`approver` 字段留痕）；`confirm_order` 门禁校验关联审批状态，非门店经理不可绕过。

## 3. 工具目录与输入输出 Schema

| 工具 | 函数 | 输入参数 | 返回结构 | 风险 | MCP 映射 |
| --- | --- | --- | --- | --- | --- |
| `mock_crm` | `get_lead` | `lead_id?` | `{lead_id, stage, source, ...}` | L0 | `crm.lead.query` |
| | `list_sessions` | — | `[{session_id, channel, ...}]` | L0 | `crm.session.list` |
| | `get_customer_history` | `customer_id?` | `[{event, time, ...}]` | L0 | `crm.history.query` |
| | `update_lead_stage` | `lead_id, stage` | `{lead_id, stage}` | L0 | `crm.lead.stage_update` |
| `mock_inventory` | `list_models` | — | `[{code, name, guide_price, stock, ...}]` | L0 | `dms.inventory.list` |
| | `check_stock` | `model_code, store_id` | `{model_code, store_id, available, stock}` | L0 | `dms.inventory.query` |
| | `reserve_car` | `model_code, store_id` | `{status:"reserved", reservation_id, ...}` | L1 | `dms.inventory.reserve` |
| `mock_price` | `get_policy` | — | `{base_discount_pct, authorized_max_discount_pct, tiers, rule}` | L0 | `pricing.policy.query` |
| | `calc_quote` | `model_code, customer_tier` | `{quote_id, final_price, guide_price, ...}` | L1 | `pricing.quote.calc` |
| | `apply_discount` | `quote_id, amount, reason` | `{status:"applied"\|"needs_approval", risk_level, approval_id?}` | L1/L2 | `pricing.discount.apply` |
| `mock_tradein` | `assess_vehicle` | `old_model?, mileage_km?` | `{assessment_id, standard_offer, trade_in_subsidy, total_trade_in_value, authorized_uplift_max}` | L0 | `tradein.vehicle.assess` |
| | `request_uplift` | `assessment_id, requested_offer, reason` | `{status:"applied"\|"needs_approval", uplift, authorized_uplift_max, approval_id?}` | L1/L2 | `tradein.valuation.uplift` |
| `mock_finance` | `calc_plan` | `price, down_payment, months` | `{price, plans:[{plan_id, monthly_payment, ...}]}` | L0 | `finance.plan.calc` |
| | `submit_approval` | `plan_id, customer_id` | `{status:"created", approval_id, risk_level:"L2"}` | L2 | `finance.approval.submit` |
| | `check_approval` | `approval_id` | `{approval_id, type, status, ...}` | L0 | `finance.approval.query` |
| | **`approve`** | `approval_id, approver, reason` | `{approval_id, status:"approved", approver, ...}` | L2 | `finance.approval.approve` |
| | **`reject`** | `approval_id, approver, reason` | `{approval_id, status:"rejected", affected_orders, ...}` | L2 | `finance.approval.reject` |
| `mock_testdrive` | `list_slots` | `store_id, model_code` | `[{slot, store_id, model_code}]` | L0 | `testdrive.slot.query` |
| | `book_slot` | `customer_id, store_id, slot, model_code` | `{status:"booked", booking_id, risk_level:"L1"}` | L1 | `testdrive.slot.book` |
| | `cancel_booking` | `booking_id` | `{status:"cancelled", booking_id}` | L1 | `testdrive.slot.cancel` |
| `mock_order` | `create_order` | `lead_id, quote_id, order_key` | `{order_id, status:"draft", risk_level:"L2", approval_refs}` | L2 | `order.create` |
| | `get_order` | `order_id` | `{order_id, status, ...}` | L0 | `order.query` |
| | `rollback_order` | `order_id` | `{status:"cancelled", rollback_point:"draft", previous_status}` | L2 | `order.rollback` |
| | **`confirm_order`** | `order_id` | `{status:"confirmed"\|"blocked", blocked_reason?}` | L2 | `order.confirm` |
| `mock_knowledge` | `search_product` | `query?` | `[{title, summary, tags, match_terms}]` | L0(rag) | `knowledge.rag.search` |
| | `search_sop` | `query?` | `[{title, summary, ...}]` | L0(rag) | `knowledge.rag.search` |
| | `search_case` | `query?` | `[{title, summary, ...}]` | L0(rag) | `knowledge.rag.search` |
| | `save_case` | `case` | `{status:"saved", case_id, ...}` | L0 | `knowledge.case.save` |
| `mock_wechat` | `get_session` | `customer_id` | `{customer_id, sessions}` | L0 | `wechat.session.query` |
| | `send_template_message` | `customer_id, template, params` | `{status:"sent", risk_level:"L1"}` | L1 | `wechat.template_message.send` |
| `mock_sms` | `send_approval_alert` | `approval_id, deal_id?, risk_type?, summary?, approver?` | `{status:"sent"\|"already_sent", channel_type, alert_key, biz_id, backend}` | L1 | `sms.approval.alert` |
| `mock_verify` | `check_deal` | `deal_id` | `{status, summary, orders, approvals, approvals_pending/approved/rejected}` | L0 | `deal.verify` |
| | **`audit_trail`** | `approval_id?, order_id?` | `[{action_id, name, risk_level, time, ...}]` | L0 | `deal.audit.query` |

> 加粗为 P2.3 新增的审批决策与审计原语。RAG 檢索（`mock_knowledge.*`）使用 TF-IDF 余弦相似度（`TFIDFRagIndex`，阈值 0.05 + Top-3），后续可平滑迁移到 PolarDB pgvector。`mock_sms.send_approval_alert` 为官方用云 Skill 封装（阿里云短信 Dysmsapi）：有 `SMS_ACCESS_KEY_ID/SECRET` 凭证真调 REST（RPC V1 签名），无凭证降级本地外呼记录（`channel_type=local_mock` 诚实标注，`tools/sms_alert.py`）。

## 4. 错误处理

- **统一错误包装**：非 2xx 返回 `{"ok": false, "error": "..."}`；Agent 按 Skill 失败处理策略降级，**禁止编造数据**。
- **函数级失败**：重试一次；仍失败输出 error span + 失败 Log（`tool_call_error`，ERROR 级），不中断管线（Worker 捕获异常继续下一步）。
- **未知工具/场景**：返回可用工具列表提示。
- **审批超时**：按未批准处理（`pending → human_handoff`），**禁止默认放行**。

## 5. 审计记录

- **结构化 actions**：每次高风险动作（`apply_discount`/`create_order`/`submit_approval`/`approve`/`reject`/`confirm_order`/`rollback_order`）经 `_action()` 写入 `actions` 列表（`action_id` + `name` + `risk_level` + `time` + 关联业务键）。
- **结构化 Log**：`_action` 同步写 `_log()`（`event` + `level` + `attributes`，WARN for L2/L3），通过 `trace_id` 与 Trace 关联。
- **append-only 审计 JSONL**：网关将 actions 追加落盘到 `run_evidence_live/{scenario_id}_audit.jsonl`（每条携带 `trace_id`），重启不丢失，可独立回放审计。
- **可查询**：`GET /tools/{sid}/audit`（支持 `?approval_id=` / `?order_id=` 筛选）；`mock_verify.audit_trail` MCP 工具等价。
- **证据归档**：`POST /tools/{sid}/archive` 快照 trace+logs+metrics 到 OSS 等价对象存储（key 含 `trace_id` 可审计回溯）。

## 6. 幂等控制

- **`create_order`**：以 `order_key`（lead_id + quote_id 组合）保证幂等；重复调用返回同一 `order_id`，防止 Agent 重复下单。
- **`approve`/`reject`**：对已决策审批（approved/rejected）返回当前状态，不二次变更（幂等）。
- **`reserve_car`**：超时自动释放（L1 可逆）。
- **`send_approval_alert`**：以 `alert_key`（=approval_id）保证幂等；同一审批单只发一次告警短信，重复调用返回 `already_sent` + 首次结果（防重发骚扰审批人）。
- **`mock_tradein.request_uplift`**：以（`assessment_id` + `requested_offer`）保证幂等；同一评估单同估值的超授权重复申请返回原审批任务（`deduplicated: true`），不重复创建（置换+金融复合场景 DEAL-2004）。
- **置换估值审批与订单门禁联动**：`request_uplift` 超授权生成的 L2 审批（`trade_in_valuation_override`）写入共享审批池，`create_order` 自动关联进 `approval_refs`，`confirm_order` 门禁自动生效——置换估值审批通过前订单禁止确认（锁单门禁）。

## 7. 回滚能力与门禁

- **回滚点**：`mock_testdrive.cancel_booking`（试驾）、`mock_order.rollback_order`（订单，回滚点 `draft`）。
- **决策与执行分离**：`reject` 标记关联订单 `rollback_requested`（决策层只标记），由执行层显式调用 `rollback_order` 回滚——避免"驳回即自动回滚"的隐式副作用。
- **confirm 门禁**：`confirm_order` 校验所有关联审批（`approval_refs`）必须 `approved` 且无 `rejected` 才允许 `draft→confirmed`；存在 pending 或 rejected 时返回 `blocked`（**高风险动作禁止默认放行**）。

## 8. 降级方式

- **工具不可用**：Agent 输出证据缺口与人工建议，不猜测数据；Skill 的失败处理策略覆盖降级路径。
- **RAG 空结果**：返回 `[]`（不编造），由 Agent 判断是否足以支撑决策（阈值 0.05 保证合法空结果）。
- **审批超时**：`pending → human_handoff`，转人工销售，禁止默认放行。
- **OSS 归档失败**：降级到本地目录 + 告警，不阻塞主链（异步执行）。

## 9. 风险分级（贯穿所有工具）

| 等级 | 语义 | 示例 | 处置 |
| --- | --- | --- | --- |
| L0 | 只读查询/检索 | 查线索、查库存、RAG 检索、查订单、查审批、审计查询 | 自动执行 |
| L1 | 低风险自动执行（可逆） | 试驾预约、库存预留、标准报价、模板消息、取消预约 | 自动执行，可回滚 |
| L2 | 审批后执行 | 超授权优惠、订单创建、征信授权、approve/reject/confirm/rollback | 生成审批任务，人工决策后执行 |
| L3 | 仅生成方案/人工执行 | 合同条款变更、大额特殊订单 | 仅生成方案，人工执行 |

## 10. 复现

```bash
# 启动网关
python3 tools/mock_tool_server.py --port 18089 &
# 审批决策 + 审计查询
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/mock_finance.reject \
  -H 'Content-Type: application/json' -d '{"approval_id":"APR-xxx","approver":"mgr","reason":"超底线"}'
curl http://127.0.0.1:18089/tools/family_suv_deal/audit
# 审批告警短信（官方用云 Skill：阿里云短信，幂等防重发）
curl -X POST http://127.0.0.1:18089/tools/family_suv_deal/mock_sms.send_approval_alert \
  -H 'Content-Type: application/json' -d '{"approval_id":"APR-xxx","deal_id":"DEAL-2001","risk_type":"discount_override","summary":"优惠超授权1.5%"}'
# MCP 等价验证（25 工具，迁移只需协议适配）
python3 tools/mcp_client_test.py
```

完整工具映射见 `tools/MCP_MAPPING.md`；机器可读目录见 `tools/tool_catalog.json`。
