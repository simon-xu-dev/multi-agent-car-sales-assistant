---
name: order-safe-execute
description: 订单创建与状态跟踪的安全执行层：幂等控制、状态机流转、审批门槛、回滚点与成交验证。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Order Safe Execute（订单安全执行）

## Purpose

当需要创建订单、跟踪订单或回滚订单时使用。订单涉及合同与交付（高风险动作），必须满足：幂等、审批门槛、回滚点、审计留痕。

## Inputs

- 报价单（quote_id、final_price）。
- 客户成交确认信息与订单幂等键（order_key）。
- 审批状态（优惠/征信审批是否通过）。

## 调用条件

- 触发：需要创建/跟踪/回滚订单、审批通过后需确认订单、或闭环完成需成交验证（check_deal）时。
- 不触发：前置条件缺失（无报价单/审批状态未知）时先补齐；审批未通过时订单只允许 draft。

## 依赖工具 / 系统

- `mock_order.create_order` / `get_order` / `rollback_order` / `confirm_order`、`mock_inventory.reserve_car`、`mock_verify.check_deal` / `audit_trail`、`mock_price.calc_quote`、`mock_finance.approve` / `reject`。
- 迁移 MCP 后对应 `order.*` / `dms.inventory.reserve` / `deal.audit.query` / `finance.approval.*`。

## Procedure

1. 校验前置条件：报价单存在、审批项状态已知、幂等键生成（lead_id + quote_id 组合）。
2. 创建订单草稿（create_order，L2）：幂等键保证重复调用返回同一订单，防止重复下单；订单快照关联当前 pending 审批（approval_refs）。
3. 高风险动作判定：合同确认、交付必须人工审批；审批前订单停留在 draft。
4. 审批决策驱动状态流转：approve → confirm_order（门禁：所有关联审批 approved 且无 rejected 才放行 draft→confirmed）；reject → 标记关联订单 rollback_requested（决策层只标记）→ 显式 rollback_order 回滚到 draft（决策与执行分离）。
5. 成交验证：调用 check_deal 汇总线索状态、订单、审批（pending/approved/rejected），输出闭环状态报告；调用 audit_trail 查询结构化审计轨迹（按 approval_id / order_id 可筛选）。

## Output Contract

```json
{
  "order": {"order_id": "ORD-...", "status": "draft|confirmed|cancelled", "risk_level": "L2", "order_key": "LEAD-2001|QUOTE-...", "approval_refs": ["APR-..."]},
  "rollback_point": "draft",
  "deal_verification": {"status": "pending_approval|won|rolled_back", "summary": "...", "approvals_pending": 0, "approvals_approved": 1, "approvals_rejected": 0},
  "audit_trail": {"total": 6, "actions": [{"action_id": "ACT-...", "name": "approve|reject_approval|confirm_order|rollback_order", "risk_level": "L2", "time": "..."}]},
  "approval_required": true
}
```

## Quality Gates

- 同一 order_key 绝不产生两个订单（幂等）。
- 审批通过前订单状态只能是 draft / pending_approval；confirm_order 门禁拒绝在存在 pending/rejected 审批时放行（高风险动作禁止默认放行）。
- 每次状态变更（approve/reject/confirm/rollback）必须写入 actions 审计轨迹（action_id + risk_level + time + 关联业务键），并通过 trace_id 与 Trace 关联。
- approve/reject 幂等——对已决策审批返回当前状态，不二次变更。

## 失败处理

- 创建失败：重试一次，仍失败输出挂起状态并告警，保留人工干预入口。
- 审批驳回：reject 标记关联订单 rollback_requested（决策层）→ 显式 rollback_order 回滚到 draft（执行层）→ 通知 negotiation-executor 重新制定方案；决策与执行分离。
- 回滚失败：标记异常订单，转人工处理，禁止静默。
- 审批超时：按未批准处理（pending → human_handoff），禁止默认放行。

## 权限与安全

- L1：回滚、状态查询。L2：订单创建（审批后确认）。L3：合同条款变更。
- 订单动作全量审计：谁创建、何时、幂等键、审批状态。

## 复用价值

"幂等 + 审批门槛 + 回滚点"是企业级订单/工单系统的通用安全模式，可复用于保险承保、房产交易、B2B 采购订单。
