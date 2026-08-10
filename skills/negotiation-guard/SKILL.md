---
name: negotiation-guard
description: 议价底线守护：记录让步轨迹、剩余额度，优惠超授权或触及底线时停止自动让步，输出审批任务或转人工交接单。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Negotiation Guard（议价风控）

## Purpose

当议价会话需要让步决策时使用。核心职责是守护底线：自动让步只在授权范围内发生，超出即停，转审批或转人工，防止销售 Agent 无限让利。

## Inputs

- 当前报价单与授权上限。
- 客户历史让步请求与已让步额度（actions 轨迹）。
- 议价底线策略（总让步上限，例如车价 3.5%）。

## 调用条件

- 触发：议价会话中收到让步请求、或任何折扣动作执行前；报价超授权上限时。
- 不触发：无报价单与授权上限（先 quote-pricing）；审批挂起时禁止继续让步。

## 依赖工具 / 系统

- `mock_price.apply_discount`（优惠执行与审批任务生成）、actions 轨迹（已让步额度）、Trace（让步留痕）。
- 议价底线策略（总让步上限，如车价 3.5%）；迁移 MCP 后对应 `pricing.discount.apply`。

## Procedure

1. 计算已让步总额与剩余授权额度。
2. 收到新让步请求时分级判定：
   - 授权内且未触底 -> 自动让步（L1），记录让步轨迹。
   - 超授权但未触底 -> 生成 L2 审批任务（discount_override）。
   - 触及底线（总让步 > 3.5% 或单次请求过大）-> 停止让步，输出转人工交接单。
3. 同一次会话对同一让步点只允许一次自动让步，防止反复让价。
4. 转人工时输出结构化交接单：客户诉求、已让步明细、剩余底线、建议人工动作。

## Output Contract

```json
{
  "concession": {"status": "escalated", "reason": "超出授权且接近底线"},
  "granted_so_far": 15000,
  "authorized_limit": 3298,
  "approval_created": {"approval_id": "APR-...", "type": "discount_override"},
  "handoff": {"to": "human-sales", "summary": "客户要求 3 万额外优惠，建议人工赠送延保权益替代现金让利"},
  "evidence_refs": ["quote:QUOTE-..."]
}
```

## Quality Gates

- 让步必须留痕：金额、额度、原因、剩余额度。
- 底线一旦触发，任何模型输出都不得继续让步。
- 转人工交接单必须包含可执行建议。

## 失败处理

- 让步记录丢失：以 Trace/actions 为准重建轨迹，缺失则暂停让步并人工核对。
- 审批超时：按未批准处理，禁止默认放行。

## 权限与安全

- 这是方案的高风险动作守护层：自动执行（L1）、审批（L2）、转人工（L3）三级边界清晰。
- 全量让步记录进入审计日志，支持事后复盘与风控分析。

## 复用价值

"底线守护 + 升级路径"可复用于保险理赔、采购议价、企业销售授权管理；是 Agent 自治能力与安全边界平衡的示范 Skill。
