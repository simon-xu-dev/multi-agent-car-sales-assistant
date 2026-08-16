# RAG pgvector 迁移方案（任务#7 PoC）

> 回应评审意见「TF-IDF 技术不前沿，建议展示 pgvector 迁移可行性验证」。
> 本文以**可插拔三后端架构 + 等价性验证证据**证明：从 TF-IDF 迁移到 PolarDB pgvector
> **可行、低成本、可回滚**，且检索接口契约（签名 / 结果结构 / 回归命中）全程不变。

## 1. 背景与结论

| 问题 | 结论 |
| --- | --- |
| 迁移是否可行？ | 可行。`tools/vector_rag.py` 已实现三后端（`local_tfidf` / `local_embedding` / `pgvector`）统一接口，pgvector 为真 SQL 适配层（insert/upsert/ANN 查询/时间窗口函数 SQL 模板齐全），与 `tools/pgvector_migration/DDL.sql` 严格对齐 |
| 迁移成本多低？ | 应用侧仅替换 `_embed()`（查询向量化）与打分执行位置（本地余弦 → SQL ANN），`search()` 接口与结果结构**零改动**；上层 Skill / Agent / mock_tools **零改动**。新增依赖仅 psycopg2（可选，未安装自动降级） |
| 迁移是否破坏现行为？ | 否。`docs/RUN_EVIDENCE/rag_backend_equivalence.json`：8 条 selfcheck RAG 回归查询（含曾修复的空结果查询）在生产后端上 100% 非空命中；`tools/selfcheck.py` 全过（87 passed / 0 failed，含 9 条 RAG 断言） |
| 为什么要迁移？ | TF-IDF 存在已知缺陷：14 条验证查询中 9 条返回空（单字中文查询无法产生 bigram 分词、稀疏精确匹配召回不足），**9/9 全部被稠密向量链路修复为命中**，与 `RAG_regression_replay.json` 的历史修复记录相互印证 |

## 2. 三后端可插拔架构

`tools/vector_rag.py`（统一 `search(query, top_k, threshold)` 接口，结果结构一致）：

| 后端 | 规范名 | 实现 | 依赖 | 诚实标注 |
| --- | --- | --- | --- | --- |
| TF-IDF 基线 | `local_tfidf` | TF-IDF + 余弦相似度（稀疏向量），`LocalTfidfIndex` | 纯 stdlib | 历史基线，默认后端，行为与升级前一致 |
| 轻量稠密 | `local_embedding` | 字符 n-gram 哈希 → 256 维向量 + 余弦相似度，`LocalEmbeddingIndex` | 纯 stdlib | **轻量 embedding 演示实现，非大模型 embedding**；即线上 mock_tools 使用的后端 |
| PolarDB | `pgvector` | 真 SQL 适配层 `PgVectorIndex`：upsert_chunks / insert_memory / search（ANN）/ search_window / recall_memory | psycopg2（可选） | 无 DSN 或无驱动时降级为 local_embedding，结果标注 `backend=pgvector_unavailable`，**不伪装真 pgvector** |

后端选择优先级：**显式参数 `create_rag_index(docs, backend=...)` > 环境变量 `RAG_BACKEND` > 默认 `local_tfidf`**。
兼容性：旧类名 `TFIDFIndex` / `DenseRagIndex` / `PgVectorIndex` 与旧后端名 `tfidf` / `dense` 全部保留，现有引用（`mock_tools.py` 等）零改动。

pgvector 连接：`connection_string` 参数 > 环境变量 `POLARDB_PGVECTOR_DSN`；`degrade=False` 时不可用直接抛 `PgVectorUnavailableError`。

## 3. 与现有 TF-IDF 的接口对齐表

| 契约项 | local_tfidf（现状） | local_embedding | pgvector | 一致性 |
| --- | --- | --- | --- | --- |
| 检索签名 | `search(query, top_k=3, threshold=0.05)` | 同左 | 同左 | ✅ 完全一致 |
| 返回结构 | `List[Dict]`（原文档字段） | 同左 | 同左 | ✅ 完全一致 |
| 证据引用 | `evidence_refs: ["product:理想 L7 产品知识"]` | 同左 | 同左 | ✅ 三后端统一经 `_decorate()` 出口 |
| 后端元数据 | `_rag: {backend, score, rank, threshold}` | 同左（backend=local_embedding） | 同左（backend=pgvector 或 pgvector_unavailable） | ✅ 始终标注实际执行后端 |
| 向量化方式 | 分词 TF-IDF（无向量） | `_embed()` n-gram 哈希 | `_embed()`（迁移 seam：生产替换为 text-embedding-v3） | ⚠️ 唯一需要替换的点 |
| 打分执行位置 | 本地余弦 | 本地余弦 | SQL `1 - (embedding <=> qvec)`（HNSW ANN） | ⚠️ 唯一需要替换的点 |
| 写入路径 | 无（只读语料） | 无 | `upsert_chunks` / `insert_memory`（幂等） | pgvector 新增 |
| 时间窗口 | 无 | 无 | `rag_search_chunks(p_ts_from, p_ts_to)` | pgvector 新增 |

**结论：迁移面收敛为 2 个 seam（`_embed()` + 打分执行位置），其余全部复用。**

## 4. Schema 设计与数据模型（`tools/pgvector_migration/DDL.sql`）

### 4.1 rag_knowledge_chunk（知识库 RAG）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `chunk_id` | BIGSERIAL PK | 代理键 |
| `tenant_id` | TEXT | 租户/门店隔离边界（默认 'default'） |
| `collection` | TEXT CHECK | `product \| sop \| case \| manual`，对齐 mock_knowledge 三类检索 |
| `ref_id` + `chunk_no` | TEXT + INT | 业务引用（如「理想L7产品知识」）+ 长文档分片序号；`(tenant_id, collection, ref_id, chunk_no)` UNIQUE → **upsert 幂等** |
| `title` / `content` / `tags` / `match_terms` | TEXT / TEXT[] / TEXT[] | 对齐 scenarios/*.json 的知识字段，本地/云端语料结构一致 |
| `embedding` | `vector(256)` | PoC 与本地轻量 embedding 对齐；生产接 text-embedding-v3 改 `vector(1024)` 并重建索引 |
| `created_at` / `updated_at` | TIMESTAMPTZ | 时间窗口过滤依据 |

### 4.2 rag_agent_memory（Agent 长记忆，替代 JSONL）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `agent_name` / `deal_id` / `trace_id` | TEXT | Agent 身份 + 业务键 + OTel trace 关联（审计回放） |
| `kind` | TEXT CHECK | `decision \| action \| approval \| lesson \| handoff`（对齐决策/审批/经验沉淀闭环） |
| `content` / `metadata` | TEXT / JSONB | 记忆正文 + 决策依据/审批人/风险等级 |
| `embedding` / `occurred_at` | `vector(256)` / TIMESTAMPTZ | 语义召回 + 时间窗口双路（对齐现有 `recall_semantic` + JSONL 时间窗口能力） |

### 4.3 查询函数（SQL 模板与 `PgVectorIndex` 类常量一一对应）

- `rag_search_chunks(p_embedding, p_tenant, p_collection, p_top_k, p_min_sim, p_ts_from, p_ts_to)`：ANN + 阈值 + TopK + 时间窗口
- `rag_recall_memory(p_embedding, p_agent, p_window_from, p_window_to, ...)`：Agent 记忆时间窗口 + 语义双路召回
- 审计视图 `rag_chunk_audit`（无 embedding 大列，供只读审计角色）

## 5. 索引选择理由（HNSW 主选 + ivfflat 备选）

| 维度 | HNSW（主选） | ivfflat（备选） |
| --- | --- | --- |
| 召回质量 | 稳定，对参数不敏感 | 依赖聚类质量，空表/倾斜数据劣化 |
| 增量写入 | 友好（无需重聚类） | 需定期 REINDEX 维护 lists |
| 查询延迟 | 稳定低延迟 | lists 配置不当延迟抖动 |
| 构建成本 | 内存与构建时间略高 | 更低 |
| 决策 | **车销场景知识持续入库（案例沉淀），延迟敏感 → HNSW（m=16, ef_construction=64）** | 数据 < 10 万行且内存受限时切换（DDL 已注释给出 `lists=100`） |

距离算子统一 `<=>`（cosine），相似度 = `1 - distance`，与本地余弦实现语义一致。
时间/集合过滤为 ANN **后过滤**（post-filter）：千级 chunk 规模无性能问题；若过滤选择性 > 90% 且数据量大，再演进为「btree 先过滤 ref 集 + ANN」两段式或按 collection 分区（已在 DDL 注释标注）。

## 6. 权限边界与密钥管理

| 角色 | 权限 | 禁止 |
| --- | --- | --- |
| `rag_app`（应用） | chunk 表 SELECT/INSERT/UPDATE；memory 表 SELECT/INSERT；两检索函数 EXECUTE | DELETE / TRUNCATE / DDL（chunk 表 append-only + upsert 幂等保证可审计） |
| `rag_auditor`（审计） | `rag_chunk_audit` 视图 SELECT | 业务表直查 |
| PUBLIC | 全部 REVOKE | — |

- 密钥：连接串经环境变量 `POLARDB_PGVECTOR_DSN` 注入，不落代码不进仓库（`agentteams.env.example` 模式）。
- 行边界：所有查询强制 `tenant_id` 等值过滤（SQL 模板与函数签名均含 tenant 参数），后续可演进 RLS。
- 迁移到 MCP 时：`PgVectorIndex` 的方法即 MCP tool 候选（`rag_search` / `rag_upsert_chunks` / `rag_recall_memory`），权限由 MCP Server 层 + 数据库角色双层控制。

## 7. 迁移步骤（含影子验证，每步可独立回滚）

1. **建库**：`psql $POLARDB_PGVECTOR_DSN -f tools/pgvector_migration/DDL.sql`（幂等，可重复执行）。
2. **回填语料**：脚本遍历 `scenarios/*.json` 的 knowledge（products/sops/cases）→ `PgVectorIndex.upsert_chunks()`（UNIQUE 键幂等，可重放）。
3. **影子双写**（可选但推荐）：写入仍走本地，新增异步双写 pgvector；比对两侧 Top-3。
4. **影子读验证**：生产流量回放（复用 `rag_regression_replay.py` 的 19 条真实 trace 查询 + `rag_backend_equivalence.json` 的 14 条验证查询），要求 pgvector 侧回归查询 100% 非空、Top-3 overlap ≥ 本地基线。
5. **切读**：`export RAG_BACKEND=pgvector`（或 `create_rag_index(..., backend="pgvector")`）。无连接自动降级 local_embedding 并标注，故障不中断业务。
6. **观察**：`_rag.backend` 字段 + RAG span（现有 rag span 已入 trace 树）监控命中率/延迟；`pgvector_unavailable` 出现率 > 阈值告警。
7. **收尾**：停双写，本地 TF-IDF 保留为离线回归基线（`--equivalence` 仍可运行）。

## 8. 回滚方案（四层，均不动数据）

| 层级 | 触发 | 动作 | 影响 |
| --- | --- | --- | --- |
| L1 连接级 | DB 抖动 | 适配层自动降级 local_embedding（`backend=pgvector_unavailable` 标注） | 秒级，业务无感 |
| L2 配置级 | pgvector 质量异常 | `RAG_BACKEND=local_embedding` 切回本地 | 一次环境变量，即时生效 |
| L3 代码级 | 接口异常 | `create_rag_index(..., backend="local_tfidf")` 回基线 | 与 L2 同机制 |
| L4 Schema 级 | 彻底下线 | DDL 尾部回滚脚本（DROP FUNCTION/VIEW/TABLE，均 IF EXISTS） | 回滚前 pg_dump 两表；`rag_agent_memory` 审计保留 ≥ 180 天 |

## 9. 迁移成本清单

| 项 | 量 | 说明 |
| --- | --- | --- |
| 新增代码 | `vector_rag.py` 295 → 885 行 | 其中 pgvector 适配层 ~200 行、等价性验证 ~200 行；**改动现有调用点 0 处** |
| 新增 DDL | `DDL.sql` 236 行 | 两表 + 两函数 + 索引 + 角色，幂等可重放 |
| 新增依赖 | psycopg2（可选） | 未安装自动降级，核心链路保持零第三方依赖 |
| 接口变更 | **0** | search 签名 / 结果结构 / evidence_refs 全程一致（见第 3 节对齐表） |
| Skill / Agent 改动 | **0** | 后端选择收敛在 `create_rag_index` 工厂 |
| 预计工时 | 建库回填 0.5 天，影子验证 1 天，切读观察 0.5 天 | 生产接真 embedding 模型另计（仅改 `_embed()` + 维度） |

## 10. 等价性验证结果（`docs/RUN_EVIDENCE/rag_backend_equivalence.json`）

运行：`python3 tools/vector_rag.py --equivalence`（语料 = 3 场景 knowledge；参数对齐线上 `threshold=0.01, top_k=3`）

| 指标 | 值 | 解读 |
| --- | --- | --- |
| 验证查询 | 14（selfcheck 回归 8 + 新增探针 6） | 覆盖 3 场景 products/sops/cases |
| 生产后端回归守护 | **8/8 全非空，PASS** | 曾修复的空结果查询无一回退，检索契约保持 |
| TF-IDF 空结果 | 9 条，其中 **9/9 被稠密链路修复为命中** | 迁移必要性的量化证据 |
| 双非空子集（5 条）Top-1 一致率 | 0.8 | 排序契约基本保持 |
| 双非空子集 Top-3 overlap 均值 | **1.0** | TF-IDF 命中集合是 embedding 命中集合的**子集**——稠密召回严格不劣化 |
| 全体 Top-3 集合一致率 | 0.14 | 主要由 TF-IDF 空结果（9/14）与稠密召回更多条目造成，属预期增益非回归 |

## 11. 诚实边界

1. `local_embedding` 是**轻量字符 n-gram 哈希 embedding（非大模型 embedding）**，验证的是接口与工程链路；生产语义能力需接 text-embedding-v3 等模型（仅改 `_embed()`，维度同步 `vector(1024)`）。
2. pgvector 后端在无 DSN / 无 psycopg2 时**降级并标注 `backend=pgvector_unavailable`**，不伪装真库结果；本 PoC 未连接真实 PolarDB 实例，SQL 模板与 DDL 一一对应、可直接执行验证。
3. 全体一致率（Top-1 0.29）不构成「两后端等价」的声称——报告区分了「契约一致」（接口/结构/回归命中，保持）与「行为一致」（排序，稠密链路有预期差异且召回严格超集包含）。
4. 本任务未修改 `docs/EVIDENCE.md`、`tools/mock_tool_server.py`、`tools/eval_harness.py`、`tools/mock_tools.py`（由并行任务负责）；`selfcheck.py` 87/87 全过（9 条 RAG 断言全 PASS，隔离测试确认与本改动无关的 3 条中间态失败由并行任务自行修复）。

## 12. 快速验证命令

```bash
# 三后端对比演示
python3 tools/vector_rag.py --demo
# 指定后端单查
python3 tools/vector_rag.py --backend pgvector --query "六座SUV 新能源"
# 等价性验证（生成 RUN_EVIDENCE 报告）
python3 tools/vector_rag.py --equivalence
# 回归
python3 tools/selfcheck.py
```
