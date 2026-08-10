---
name: profile-building
description: 从会话文本、历史互动与相似案例中构建结构化客户画像（家庭结构、预算、用车场景、决策角色），输出置信度与证据引用。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Profile Building（画像构建）

## Purpose

当需要为一条线索生成可决策的客户画像时使用。画像字段必须带证据与置信度，防止凭单一渠道信息猜测客户需求。

## Inputs

- 归并后的线索会话文本。
- 客户历史互动记录（到店、对比、试驾、保养、续保、活动）。
- 相似客户成交案例（可选参考）。

## 调用条件

- 触发：线索完成归并后首次画像构建；画像字段缺失、置信度不足或客户产生新互动需要更新时。
- 不触发：已有高置信度画像且无新信息；敏感字段（收入/征信）缺失时不推断、只标注。

## 依赖工具 / 系统

- `mock_crm.get_lead` / `get_customer_history`（Agent 记忆存储）、`mock_knowledge.search_case`（知识库 RAG）。
- 画像 Schema（family_structure / budget_range / use_case / key_preferences / decision_role / confidence）。

## Procedure

1. 从会话中抽取画像字段：家庭结构、预算区间、用车场景、偏好、决策角色。
2. 用历史互动记录交叉验证（如到店记录佐证六座偏好）。
3. 检索相似成交案例，补充画像推断依据。
4. 为每个字段标注置信度（高/中/低）与证据引用。
5. 低置信度字段进入 data_gaps，明确告知下游信息不足。

## Output Contract

```json
{
  "lead_id": "LEAD-2001",
  "profile": {
    "family_structure": "二胎家庭 4 人",
    "budget_range": "25-28 万",
    "use_case": "家庭自驾游",
    "key_preferences": ["六座", "空间", "安全", "新能源"],
    "decision_role": "夫妻共同决策"
  },
  "confidence": 0.85,
  "data_gaps": ["旧车评估意愿未知"],
  "evidence_refs": ["session:website@09:40"]
}
```

## Quality Gates

- 画像字段必须有证据引用，无证据字段必须进入 data_gaps。
- 置信度 < 0.5 的画像不得直接驱动策略生成。
- 敏感字段（收入、征信）禁止推断。

## 失败处理

- 历史记录为空：仅使用会话内显式信息，置信度上限 0.6。
- 会话信息冲突：保留冲突项并转人工，不自行取舍。

## 权限与安全

- 全程 L0 只读；客户个人信息按最小化原则使用，输出脱敏摘要。

## 复用价值

画像 Schema 与证据机制可直接复用于保险核保、房产需求分析等高客单价决策场景；是 RAG「Agent 记忆存储」的消费者。
