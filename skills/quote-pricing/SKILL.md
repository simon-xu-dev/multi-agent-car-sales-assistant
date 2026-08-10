---
name: quote-pricing
description: 在政策授权范围内生成标准报价与优惠方案；超出授权的优惠自动升级为 L2 审批任务。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Quote Pricing（报价与优惠）

## Purpose

当需要向客户输出报价或处理优惠申请时使用。报价必须由政策（基础优惠 + 车型补贴 + 客户等级优惠）计算得出，超授权优惠不得自动应用。

## Inputs

- 报价政策（base_discount_pct、tiers、authorized_max_discount_pct）。
- 车型指导价与补贴。
- 客户等级（normal / silver / gold）。

## 调用条件

- 触发：需要向客户输出报价或处理优惠申请时；策略生成需测算价格区间时。
- 不触发：无有效报价政策；审批挂起时禁止将未批准优惠计入最终报价。

## 依赖工具 / 系统

- `mock_price.get_policy`（政策）、`mock_price.calc_quote`（报价计算）、`mock_price.apply_discount`（优惠与审批升级）。
- 政策数据源（base_discount_pct / tiers / authorized_max_discount_pct）；迁移 MCP 后对应 `pricing.*`。

## Procedure

1. 读取报价政策，按公式计算标准报价：指导价 - 基础优惠 - 补贴 - 等级优惠。
2. 输出报价单（quote_id、明细、最终价、授权上限）。
3. 客户申请额外优惠时：金额 ≤ 授权上限 -> 自动应用（L1）；金额 > 授权上限 -> 生成 L2 审批任务并挂起。
4. 审批前不得把未批准优惠计入最终报价。

## Output Contract

```json
{
  "quote_id": "QUOTE-...",
  "model_code": "L7",
  "guide_price": 329800,
  "base_discount": 2638,
  "subsidy": 8000,
  "final_price": 319162,
  "authorized_max_discount_pct": 1.0,
  "discount_override": {"status": "needs_approval", "approval_id": "APR-...", "risk_level": "L2"}
}
```

## Quality Gates

- 报价必须来自政策计算，禁止"感觉定价"。
- 超授权优惠必须生成审批任务，任何情况下不得静默放行。
- 报价单必须包含授权上限，让下游 Agent 可判定风险。

## 失败处理

- 政策读取失败：停止报价并转人工，禁止使用缓存外的假设数据。
- 审批任务创建失败：重试一次，仍失败则升级人工，不得继续让价。

## 权限与安全

- L1 自动执行范围：标准报价、授权内优惠。
- L2 审批范围：超授权优惠。所有优惠动作写入审计日志（actions + Trace）。

## 复用价值

"授权额度 + 审批升级"模式适用于所有定价敏感行业（保险、零售、房产）；报价单契约可对接真实价格系统与 MCP。
