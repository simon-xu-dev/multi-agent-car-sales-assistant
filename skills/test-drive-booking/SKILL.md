---
name: test-drive-booking
description: 查询试驾档期并自动预约（L1 可逆动作），失败重试并推荐替代档期，支持取消回滚。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Test Drive Booking（试驾预约）

## Purpose

当客户表达试驾意愿或策略要求安排试驾时使用。预约属于低风险可逆动作（L1），可自动执行；预约失败时推荐替代档期，不阻塞闭环。

## Inputs

- 客户 ID 与门店。
- 目标车型与档期偏好（如有）。

## 调用条件

- 触发：客户表达试驾意愿、策略要求安排试驾、或试驾需改期/取消时。
- 不触发：无可用门店或车型（先确认库存）；客户未同意替代档期时不强行预约。

## 依赖工具 / 系统

- `mock_testdrive.list_slots` / `book_slot` / `cancel_booking`（档期与预约）、`mock_crm.update_lead_stage`（状态同步）。
- 迁移 MCP 后对应 `testdrive.slot.*`。

## Procedure

1. 查询指定门店与车型的可用档期（list_slots）。
2. 优先客户偏好档期，无则推荐最近可用档期。
3. 执行预约（book_slot），返回 booking_id。
4. 预约成功后同步更新线索状态为 test_driving（update_lead_stage）。
5. 如客户取消，执行 cancel_booking 回滚并释放档期。

## Output Contract

```json
{
  "booking_id": "BK-XXXX",
  "customer_id": "CUST-2001",
  "store_id": "store_001",
  "slot": "2026-08-08 14:00",
  "model_code": "L7",
  "status": "booked",
  "risk_level": "L1"
}
```

## Quality Gates

- 预约必须确认档期真实存在（来自 list_slots 结果），禁止虚构档期。
- 预约后必须更新线索状态机，保证共享状态一致。
- 取消必须走 cancel_booking 完成回滚，不留孤儿预约。

## 失败处理

- 目标档期满：重试一次并推荐替代档期；客户不同意则保留线索至 negotiation-executor 转人工。
- 预约接口失败：重试一次，仍失败则输出人工预约建议，不阻塞其他闭环动作。

## 权限与安全

- L1 自动执行；预约信息写入 Trace，支持审计与回滚。
- 不涉及资金与承诺，取消无成本。

## 复用价值

"档期查询 + 预约 + 回滚"模式可复用于房产看房、医疗服务预约、4S 店售后工位预约等场景。
