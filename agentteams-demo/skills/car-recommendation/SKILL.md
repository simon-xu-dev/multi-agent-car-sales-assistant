---
name: car-recommendation
description: 基于画像匹配 2-3 款候选车型，输出对比矩阵、推荐理由与库存可用性，推荐理由必须引用产品知识证据。
metadata:
  version: "0.1.0"
  maturity: demo
  type: custom-skill
---

# Car Recommendation（车型推荐）

## Purpose

当画像与意图分级完成后需要推荐具体车型时使用。推荐必须由画像 + 产品知识 + 库存共同支撑，不允许无证据推荐。

## Inputs

- 客户画像（家庭结构、预算、偏好、用车场景）。
- 车型目录与库存（mock_inventory）。
- 产品知识库检索结果（mock_knowledge.search_product）。

## 调用条件

- 触发：画像与意图分级完成后需要推荐车型时；客户需求变更需重新匹配时。
- 不触发：画像置信度 < 0.5（先补画像）；知识库无检索结果时只输出目录基础信息并标注。

## 依赖工具 / 系统

- `mock_inventory.list_models` / `check_stock`（车型目录与库存）、`mock_knowledge.search_product`（产品知识 RAG）。
- 产品知识库（车型参数/配置/竞品对比文档）。

## Procedure

1. 按预算区间过滤车型目录。
2. 按画像关键偏好排序：空间/安全/新能源/智能等标签匹配。
3. 输出 2-3 款候选的对比矩阵（价格、空间、续航、安全、适用性）。
4. 每款候选给出匹配理由，引用产品知识证据与库存状态。
5. 库存不足的车型明确标注，避免承诺无法兑现。

## Output Contract

```json
{
  "recommendations": [
    {
      "model": "理想 L7",
      "category": "中大型增程 SUV",
      "guide_price": 329800,
      "match_reason": "六座 + 安全 + 智能，贴合二胎家庭",
      "stock_ok": true,
      "evidence_refs": ["product:L7"]
    }
  ]
}
```

## Quality Gates

- 推荐数量必须 2-3 款，单款推荐必须给出差异化理由。
- 推荐理由必须引用产品文档或案例证据。
- 客户预算与推荐价格区间偏差 > 20% 时必须说明原因。

## 失败处理

- 知识库检索无结果：只输出车型目录基础信息并标注"知识不足"，不编造参数。
- 库存查询失败：标注库存未知，禁止承诺交付时间。

## 权限与安全

- L0 只读动作；不涉及报价承诺（报价由 quote-pricing 负责）。

## 复用价值

推荐引擎与证据引用机制可复用于房产选房、保险产品匹配等场景；RAG 检索证据是决策可信度的核心来源。
