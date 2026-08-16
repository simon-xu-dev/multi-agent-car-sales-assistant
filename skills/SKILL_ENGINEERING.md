# Skill 工程体系

> 本文件说明 Skill 层的版本管理、依赖图、失败处理策略、质量门禁与治理设计。
> 机器可读注册表见 `skill_registry.json`。

## 1. Skill 依赖图

```
lead-fusion ─────→ profile-building ─────→ intent-scoring ─────→ car-recommendation
                        │                       │                       │
                        └──→ deal-memory ←──────┘                       │
                              │    ↑                                    │
                              │    │                                    ↓
                              │    └── case-mining ←── order-safe-execute ←── quote-pricing
                              │              │              ↑                   │
                              └──────────────┘              │                   │
                                                            │                   ↓
                                                     negotiation-guard ←── quote-pricing
                                                            │
                                                            ↓
                                                     finance-plan ──→ order-safe-execute

test-drive-booking（独立，无 Skill 依赖）
evidence-archive（横切，可被任何 Agent 异步调用）
deal-memory（基础能力，被 6 个 Skill 依赖）
```

### 依赖矩阵

| Skill | 依赖 Skill | 被依赖 Skill | 依赖工具数 | 风险等级 |
|---|---|---|---|---|
| lead-fusion | — | profile-building, intent-scoring | 4 | L0 |
| profile-building | lead-fusion, deal-memory | intent-scoring, car-recommendation | 3 | L0 |
| intent-scoring | profile-building, deal-memory | car-recommendation, quote-pricing | 2 | L0 |
| car-recommendation | profile-building, deal-memory | quote-pricing | 3 | L0 |
| quote-pricing | car-recommendation, deal-memory | negotiation-guard, finance-plan, order-safe-execute | 3 | L1/L2 |
| negotiation-guard | quote-pricing | order-safe-execute | 1 | L1/L2/L3 |
| test-drive-booking | — | — | 4 | L1 |
| finance-plan | quote-pricing | order-safe-execute | 3 | L1/L2 |
| order-safe-execute | quote-pricing, negotiation-guard | case-mining | 5 | L1/L2/L3 |
| case-mining | deal-memory | — | 4 | L0 |
| deal-memory | — | 6 个 Skill | 2 | L0 |
| evidence-archive | — | — | 1 (OSS REST) | L0 |

### 关键路径

**成交主链**：lead-fusion → profile-building → intent-scoring → car-recommendation → quote-pricing → negotiation-guard → order-safe-execute → case-mining

**最长路径**：8 个 Skill 串行，任何一环失败将阻断主链。每环均有降级策略（见 §3），保证"降级不阻断"。

## 2. 版本管理

### 2.1 版本号规范

采用 SemVer（语义化版本）：`MAJOR.MINOR.PATCH`

| 变更类型 | 版本递增 | 示例 |
|---|---|---|
| 输入/输出 Schema 不兼容变更 | MAJOR | 0.x → 1.0.0 |
| 新增可选字段、新增失败处理分支 | MINOR | 0.1.0 → 0.2.0 |
| Prompt 调优、阈值微调、文档修正 | PATCH | 0.1.0 → 0.1.1 |

### 2.2 发布流程

```
Skill 作者修改 SKILL.md → 更新 skill_registry.json version
    → Nacos AI Registry 注册（FORMAL 门禁审核）
        → 灰度发布（10% → 50% → 100%）
            → 全量上线
```

### 2.3 回滚策略

- Nacos AI Registry 支持多版本共存，秒级回滚到上一版本
- 回滚触发条件：Golden 评估准确率下降 > 5%、LLM-as-Judge 评分下降 > 10%、工具调用失败率上升 > 3%
- 回滚不影响已创建的订单/审批状态（幂等保证）

### 2.4 当前版本状态

| Skill | 当前版本 | 成熟度 | 状态 |
|---|---|---|---|
| lead-fusion | 0.1.0 | demo | 初赛验证 |
| profile-building | 0.1.0 | demo | 初赛验证 |
| intent-scoring | 0.1.0 | demo | 初赛验证 |
| car-recommendation | 0.1.0 | demo | 初赛验证 |
| quote-pricing | 0.1.0 | demo | 初赛验证 |
| negotiation-guard | 0.1.0 | demo | 初赛验证 |
| test-drive-booking | 0.1.0 | demo | 初赛验证 |
| finance-plan | 0.1.0 | demo | 初赛验证 |
| order-safe-execute | 0.1.0 | demo | 初赛验证 |
| case-mining | 0.1.0 | demo | 初赛验证 |
| deal-memory | 0.1.0 | demo | 初赛验证 |
| evidence-archive | 0.2.0 | demo | OSS REST 已验证 |

## 3. 失败处理策略（代码级）

### 3.1 统一失败处理框架（已落地：`mock_tools.py` SkillFailureHandler + `mock_tool_server.py` call_tool 集成）

```python
# mock_tools.py: SkillFailureHandler 类（代码级实现，非伪代码）
class SkillFailureHandler:
    RETRYABLE_KEYWORDS = {"timeout", "rate_limit", "transient", "connection", "503", "429"}
    NON_RETRYABLE_KEYWORDS = {"auth", "invalid", "not_found", "permission", "forbidden"}

    @staticmethod
    def classify(error: Exception) -> str: ...  # retryable / non_retryable / unknown

    @staticmethod
    def handle(tool_name: str, error: Exception, attempt: int = 1) -> dict:
        # retryable + 还有重试次数 → 返回 {"retry": True}
        # non_retryable → 返回 {"status": "failed", "gap": ..., "suggestion": ...}
        # 重试耗尽/未知 → 返回 {"status": "degraded", "gap": ..., "alert": True}
```

```python
# mock_tool_server.py: call_tool() 集成
# 工具调用异常时：
#   1. SkillFailureHandler.classify() 分类错误类型
#   2. retryable → 重试一次（max_retries=1）
#   3. 重试耗尽 / non_retryable → 返回结构化降级响应（不抛异常，保证主链不阻断）
#   4. 降级响应写入 Trace（status=degraded）+ Log（event=tool_call_degraded）
```

### 3.2 各 Skill 失败处理明细

| Skill | 失败场景 | 处理策略 | 降级输出 |
|---|---|---|---|
| lead-fusion | 会话缺客户 ID | 启发式归并 + 置信度标注 | 疑似重复候选列表 |
| lead-fusion | 归并歧义 | 保留候选转人工 | 不丢弃任何会话 |
| profile-building | 无历史记录 | 置信度上限 0.6 | 画像 + data_gaps |
| profile-building | 信息冲突 | 转人工确认 | 冲突标注 |
| intent-scoring | 信号不足 | 低置信度分级 | nurture + 补充采集建议 |
| car-recommendation | KB 空结果 | 仅目录基础信息 | 标注"知识不足" |
| car-recommendation | 库存未知 | 标注库存未知 | 不推荐无库存车型 |
| quote-pricing | 政策不可用 | 停止报价转人工 | 证据缺口 |
| quote-pricing | 审批创建失败 | 重试一次后升级 | 人工审批建议 |
| negotiation-guard | 让步记录丢失 | Trace 重建 | 暂停让步 |
| negotiation-guard | 审批超时 | 按未批准处理 | 不默认放行 |
| order-safe-execute | 创建失败 | 重试一次后挂起 | 告警 |
| order-safe-execute | 回滚失败 | 标记异常 | 转人工 |
| evidence-archive | OSS 不可用 | 降级本地 | store_type=local |
| deal-memory | 检索超时 | 降级无记忆参考 | 标注"无记忆" |

### 3.3 重试策略

| 策略 | 适用 Skill | max_retries | backoff |
|---|---|---|---|
| 不重试 | negotiation-guard, test-drive-booking | 0 | — |
| 重试一次（无退避） | lead-fusion, profile-building, intent-scoring, car-recommendation, case-mining, deal-memory | 1 | none |
| 重试一次（指数退避） | quote-pricing, finance-plan, order-safe-execute, evidence-archive | 1 | exponential |

## 4. 质量门禁

### 4.1 发布前检查

- **Golden 评估**：13/13 准确率必须保持 1.0
- **Badcase 评估**：7/7 精确率必须保持 1.0
- **LLM-as-Judge**：tool_selection ≥ 9/10, risk_compliance ≥ 10/10, rag_relevance ≥ 8/10
- **selfcheck 回归**：56/56 断言必须全通过
- **幂等验证**：create_order 重复调用返回同一 order_id
- **门禁校验**：reject 后 confirm 必须被拦截

### 4.2 运行时监控

| 指标 | 阈值 | 告警 |
|---|---|---|
| 工具调用成功率 | < 95% | WARN |
| 工具调用成功率 | < 90% | ERROR |
| 端到端时延 | > 30s | WARN |
| RAG 空结果率 | > 20% | WARN |
| 审批超时率 | > 5% | ERROR |

## 5. 治理设计（Nacos AI Registry 映射）

| 治理维度 | 当前实现 | 后续迁移 |
|---|---|---|
| 注册发现 | `skill_registry.json` 本地文件 | Nacos AI Registry 服务注册 |
| 版本管理 | SemVer + skill_registry.json version 字段 | Nacos 多版本共存 + 灰度发布 |
| 权限控制 | 风险分级 L0-L3 内嵌于 Skill | Nacos 三层权限隔离 |
| 审计追溯 | append-only JSONL + trace_id 关联 | Nacos 全链路审计 |
| 回滚能力 | 本地文件版本回退 | Nacos 秒级回滚 |
| 质量评估 | Golden/Badcase + LLM-as-Judge | Nacos + AgentLoop 自动化评估 |
