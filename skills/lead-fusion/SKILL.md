---
name: lead-fusion
description: 将官网、微信、电话、短视频、门店等多渠道客户咨询按客户维度归并、去重、清洗并分级，输出统一线索候选。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Lead Fusion（线索归并）

## Purpose

当收到多条跨渠道的客户会话（官网咨询、企业微信、电话转写、抖音私信、门店记录）时，判断它们是否属于同一客户、同一购车需求，合并为一条线索并给出分级建议。

## Inputs

- 多渠道会话列表（channel / customer_id / time / text / owner）。
- 线索元数据（来源、门店、预算提示）。

## 调用条件

- 触发：lead-intake 收到新会话流、或出现 2+ 条跨渠道会话疑似同客户时。
- 不触发：单条独立会话且无重复嫌疑；身份无法确认时不强制合并（标注疑似重复）。

## 依赖工具 / 系统

- `mock_crm.list_sessions` / `get_lead` / `update_lead_stage`、`mock_wechat.get_session`。
- 会话契约（channel / customer_id / time / text / owner）；迁移 MCP 后对应 `crm.lead.query`。

## Procedure

1. 归一化时间、渠道名、客户 ID 与需求关键词。
2. 按客户 ID 或「联系方式 + 时间窗口（48h）+ 需求主题」聚类会话。
3. 对同一客户的多条会话合并去重，保留信息最全的会话为锚点。
4. 输出合并线索：来源渠道、需求摘要、初始分级建议。
5. 无法确认同一身份的会话不强制合并，标注为疑似重复。

## Output Contract

```json
{
  "lead_id": "LEAD-2001",
  "source_channels": ["website", "wechat", "phone"],
  "dedup_summary": "3 条会话归并为 1 条线索",
  "initial_stage": "qualified",
  "intent_hint": "家庭 SUV 购车咨询",
  "evidence_refs": ["session:website@09:40"]
}
```

## Quality Gates

- 同一客户跨渠道会话必须合并，不允许同一客户出现两条并列线索。
- 不同客户即使咨询相似车型，也不得合并。
- 每条 evidence_ref 必须可追溯到原始会话。

## 失败处理

- 会话缺失客户 ID：按「联系方式 + 时间窗口」启发式归并并标注置信度，不硬合并。
- 归并歧义：保留两条候选并转人工确认，不丢弃任何会话。

## 权限与安全

- L0 只读动作；update_lead_stage 为状态机流转（L0），不涉及资金与承诺。
- 会话内容脱敏后进入下游，禁止输出完整电话号码。

## 复用价值

可复用于保险、房产、高客单价零售等任何多渠道线索型业务；与渠道系统解耦，仅依赖会话契约。
