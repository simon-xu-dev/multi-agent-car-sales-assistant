---
name: case-mining
description: 从成交闭环报告与执行证据中提炼可复用案例（画像、路径、关键动作、结果、风险点），脱敏后写入知识库。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Case Mining（案例提炼沉淀）

## Purpose

当一份成交/流失/转人工闭环完成后，需要把过程与经验沉淀为可检索的知识时使用。这是"经验 -> 知识 -> 决策"回流闭环的写入端。

## Inputs

- 成交闭环报告（影响面、路径、动作、审批、结果）。
- 工具调用 Trace 与 actions（执行证据）。
- 既有案例库（判断增量价值）。

## 调用条件

- 触发：成交/流失/转人工闭环完成、TeamLeader 汇总报告输出后；运营效果好的触达策略需沉淀时。
- 不触发：证据不足时仅沉淀经验摘要；重复案例（增量判断无价值）不重复入库。

## 依赖工具 / 系统

- `mock_knowledge.search_case`（增量判断）/ `save_case`（入库）、`mock_crm.get_lead` / `update_lead_stage`（线索终态）。
- 执行证据：工具调用 Trace 与 actions；后续版本经 Nacos AI Registry 审核发布。

## Procedure

1. 从报告中提取案例要素：客户画像摘要、跟进路径、关键动作、结果指标、风险点。
2. 检索既有案例（search_case），判断增量价值，避免重复入库。
3. 脱敏（移除姓名、电话、地址等个人标识）后写入知识库（save_case）。
4. 输出 Skill / SOP 更新建议（仅建议，由管理员审核发布）。

## Output Contract

```json
{
  "case_id": "CASE-...",
  "title": "2026-08 家庭 SUV 成交案例",
  "summary": "六座需求客户，试驾前置促成成交",
  "key_actions": ["试驾前置", "置换补贴测算"],
  "risk_learnings": ["价格敏感客户让步必须留证据"],
  "skill_updates": ["car-recommendation 增加家庭画像模板"],
  "evidence_refs": ["trace:family_suv_deal"]
}
```

## Quality Gates

- 入库案例必须脱敏：禁止包含客户姓名、电话、完整地址。
- 每个关键动作必须能追溯到 Trace 证据。
- 重复内容不重复入库（增量判断）。

## 失败处理

- 证据不足：案例标注"证据不完整"，仅沉淀经验摘要，不沉淀具体数据结论。
- 入库失败：重试一次，仍失败输出告警，保留草稿供人工入库。

## 权限与安全

- 写入动作 L0（知识库写操作）；涉及策略变更的建议必须人工审核后发布。
- 案例数据脱敏合规是红线：个人数据授权边界严格遵循赛事合规要求。

## 复用价值

案例沉淀机制是方案"知识持续优化"的核心；可配合 Nacos AI Registry 做 Skill 版本管理与灰度发布。
