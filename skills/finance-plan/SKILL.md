---
name: finance-plan
description: 生成金融方案对比（低息 / 银行分期）；征信授权与合同签署必须走 L2 审批，审批通过前订单仅保留草稿。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Finance Plan（金融方案）

## Purpose

当客户需要分期购车或对月供敏感时使用。金融方案计算属于 L1；涉及征信授权与合同签署属于 L2 审批，涉及个人数据必须人工审批并留痕。

## Inputs

- 车型最终成交价。
- 客户首付预算与期望期数。
- 金融产品目录（厂家低息 / 银行分期）。

## 调用条件

- 触发：客户对分期/月供敏感需要输出金融方案时；客户确认方案需发起征信审批时。
- 不触发：客户明确全款；客户未授权时禁止调用征信审批动作。

## 依赖工具 / 系统

- `mock_finance.calc_plan`（方案计算）、`mock_finance.submit_approval` / `check_approval`（征信 L2 审批）。
- 金融产品目录（厂家低息/银行分期）；迁移 MCP 后对应 `finance.*`。

## Procedure

1. 计算每组金融方案：贷款额、月供、总利息（等额本息）。
2. 输出 2 组方案对比（低息 vs 银行分期），标注月供差异。
3. 客户确认方案后，发起征信授权审批（submit_approval，L2）。
4. 审批通过前订单停留在草稿状态（order-safe-execute 约束），审批结果由 check_approval 查询。
5. 全程遵守征信数据使用边界：仅用于金融审批，禁止用于营销。

## Output Contract

```json
{
  "plans": [
    {"product": "厂家低息金融", "loan": 100000, "months": 36, "monthly_payment": 2907, "total_interest": 4652},
    {"product": "合作银行分期", "loan": 100000, "months": 36, "monthly_payment": 2952, "total_interest": 6272}
  ],
  "approval": {"approval_id": "APR-...", "type": "credit_authorization", "risk_level": "L2", "status": "pending"}
}
```

## Quality Gates

- 月供计算必须可复算（公式与参数随结果输出）。
- 征信授权未通过前，禁止创建正式订单。
- 客户未授权时禁止调用征信相关审批动作。

## 失败处理

- 审批超时/失败：按未批准处理，输出"等待人工审批"状态，不默认通过。
- 方案计算异常：重算一次，仍异常则输出估算区间并转人工。

## 权限与安全

- L1：方案计算（纯算术）。L2：征信授权、合同签署。
- 征信数据最小化使用，审批记录审计留痕（附录红线：个人信息合规边界）。

## 复用价值

金融方案计算 + 审批门禁模式可复用于房产按揭、保险分期、3C 消费金融等场景；征信合规边界是行业级模板。
