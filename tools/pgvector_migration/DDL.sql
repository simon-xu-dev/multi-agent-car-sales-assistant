-- =============================================================================
-- SalesFlow RAG → PolarDB pgvector 迁移 DDL
-- 兼容性：PostgreSQL 11+ / PolarDB PostgreSQL 版（pgvector 扩展）
-- 对齐性：与 tools/vector_rag.py 中 PgVectorIndex 的 SQL 模板严格一一对应
--   - SQL_UPSERT_CHUNK        → rag_knowledge_chunk（UNIQUE 键幂等 upsert）
--   - SQL_SEARCH_ANN          → rag_knowledge_chunk + HNSW 余弦索引
--   - SQL_SEARCH_WINDOW       → rag_search_chunks(...)（时间窗口 ANN 函数）
--   - SQL_INSERT_MEMORY       → rag_agent_memory
--   - SQL_SEARCH_MEMORY_WINDOW→ rag_recall_memory(...)（时间窗口 + 语义双路召回）
--
-- 维度说明（诚实标注）：
--   vector(256) 与本地轻量 embedding（字符 n-gram 哈希，vector_rag.py）对齐，
--   用于 PoC 演示与等价性验证。生产接入 text-embedding-v3 等模型时改为
--   vector(1024)，仅需：ALTER 列维度（或新建表）+ 重新生成向量 + 重建索引，
--   应用侧只改 _embed()，SQL 模板与检索接口不变。
--
-- 索引选择（见 docs/RAG_PGVECTOR_MIGRATION.md 第 5 节）：
--   主选 HNSW（召回/延迟稳定、无需预聚类、对增量写入友好）；
--   ivfflat 作为数据量 < 10 万行且内存受限时的备选（注释给出）。
--   检索距离算子：<=> （cosine distance），相似度 = 1 - distance。
--
-- 执行方式：psql "postgres://user:pwd@host:5432/db" -f DDL.sql
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. 扩展
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;

-- -----------------------------------------------------------------------------
-- 1. 知识 chunk 表（产品知识 / SOP / 成交案例 / 手册，多租户隔离）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_knowledge_chunk (
    chunk_id     BIGSERIAL    PRIMARY KEY,
    tenant_id    TEXT         NOT NULL DEFAULT 'default',          -- 租户/门店边界
    collection   TEXT         NOT NULL,                            -- product|sop|case|manual
    ref_id       TEXT         NOT NULL,                            -- 业务引用（如 理想L7产品知识）
    chunk_no     INT          NOT NULL DEFAULT 0,                  -- 长文档分片序号
    title        TEXT         NOT NULL,
    content      TEXT         NOT NULL,
    tags         TEXT[]       NOT NULL DEFAULT '{}',
    match_terms  TEXT[]       NOT NULL DEFAULT '{}',               -- 对齐本地实现的 match_terms 字段
    embedding    vector(256)  NOT NULL,
    source       TEXT         NOT NULL DEFAULT 'scenarios',        -- 数据来源（scenarios/CRM/DMS）
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT rag_chunk_collection_chk CHECK (collection IN ('product', 'sop', 'case', 'manual')),
    CONSTRAINT rag_knowledge_chunk_uidx UNIQUE (tenant_id, collection, ref_id, chunk_no)
);

COMMENT ON TABLE  rag_knowledge_chunk IS '知识库 RAG chunk 表：embedding 由 _embed() 生成（生产=text-embedding-v3，PoC=n-gram 哈希 256 维）';
COMMENT ON COLUMN rag_knowledge_chunk.embedding IS 'vector(256) 为 PoC 维度；生产接 text-embedding-v3 改 vector(1024) 并重建索引';

-- 1.1 ANN 索引（主选 HNSW，余弦距离）
CREATE INDEX IF NOT EXISTS idx_rag_chunk_hnsw
    ON rag_knowledge_chunk
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 备选 ivfflat（数据 < 10 万行、内存受限时启用；需在有一定数据后再建，避免空表聚类劣化）：
-- CREATE INDEX IF NOT EXISTS idx_rag_chunk_ivfflat
--     ON rag_knowledge_chunk
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);

-- 1.2 时间窗口 / 集合过滤支撑索引（rag_search_chunks 的 created_at 范围过滤）
CREATE INDEX IF NOT EXISTS idx_rag_chunk_collection_time
    ON rag_knowledge_chunk (tenant_id, collection, created_at DESC);

-- 会话级召回率调节（HNSW 后过滤场景建议适当调高；默认 40）
-- SET hnsw.ef_search = 40;

-- -----------------------------------------------------------------------------
-- 2. 时间窗口 ANN 查询函数（对齐 PgVectorIndex.SQL_SEARCH_WINDOW）
--    语义：相似度 = 1 - (embedding <=> p_embedding)，阈值 + TopK + created_at 范围
--    诚实标注：时间/集合过滤为 ANN 后过滤（post-filter）。
--    当前语料规模（千级 chunk）无性能问题；若过滤选择性 > 90% 且数据量大，
--    建议改两段式（先按 btree 过滤 ref 集再 ANN）或按 collection 分区。
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION rag_search_chunks(
    p_embedding  vector(256),
    p_tenant     TEXT        DEFAULT 'default',
    p_collection TEXT        DEFAULT NULL,
    p_top_k      INT         DEFAULT 3,
    p_min_sim    FLOAT8      DEFAULT 0.01,
    p_ts_from    TIMESTAMPTZ DEFAULT NULL,
    p_ts_to      TIMESTAMPTZ DEFAULT NULL
)
RETURNS TABLE (
    chunk_id    BIGINT,
    collection  TEXT,
    ref_id      TEXT,
    title       TEXT,
    tags        TEXT[],
    match_terms TEXT[],
    similarity  FLOAT8
)
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT c.chunk_id, c.collection, c.ref_id, c.title, c.tags, c.match_terms,
           1 - (c.embedding <=> p_embedding) AS similarity
    FROM rag_knowledge_chunk c
    WHERE c.tenant_id = p_tenant
      AND (p_collection IS NULL OR c.collection = p_collection)
      AND (p_ts_from IS NULL OR c.created_at >= p_ts_from)
      AND (p_ts_to   IS NULL OR c.created_at <  p_ts_to)
      AND 1 - (c.embedding <=> p_embedding) >= p_min_sim
    ORDER BY c.embedding <=> p_embedding
    LIMIT GREATEST(p_top_k, 1);
$$;

COMMENT ON FUNCTION rag_search_chunks IS 'RAG ANN 检索：余弦相似度阈值 + TopK + 时间窗口（对齐 vector_rag.PgVectorIndex.SQL_SEARCH_WINDOW）';

-- -----------------------------------------------------------------------------
-- 3. Agent 记忆表（会话历史与决策上下文：时间窗口 + 语义双路召回）
--    对齐 mock_tools 现有 JSONL 记忆（时间窗口查询 + TF-IDF 语义召回）→ PolarDB 长记忆
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_agent_memory (
    memory_id    BIGSERIAL    PRIMARY KEY,
    tenant_id    TEXT         NOT NULL DEFAULT 'default',
    agent_name   TEXT         NOT NULL,                 -- 如 negotiation-executor
    deal_id      TEXT         NOT NULL,                 -- 业务键（DEAL-2001）
    trace_id     TEXT,                                  -- 与 OTel trace 关联（审计回放）
    kind         TEXT         NOT NULL,                 -- decision|action|approval|lesson|handoff
    content      TEXT         NOT NULL,
    metadata     JSONB        NOT NULL DEFAULT '{}',    -- 决策依据/审批人/风险等级等
    embedding    vector(256)  NOT NULL,
    occurred_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT rag_memory_kind_chk CHECK (kind IN ('decision', 'action', 'approval', 'lesson', 'handoff'))
);

COMMENT ON TABLE rag_agent_memory IS 'Agent 记忆存储：时间窗口查询 + 向量语义召回，trace_id 关联可观测体系，替代本地 JSONL 长记忆';

CREATE INDEX IF NOT EXISTS idx_memory_hnsw
    ON rag_agent_memory
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_memory_time
    ON rag_agent_memory (tenant_id, agent_name, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_deal
    ON rag_agent_memory (tenant_id, deal_id);

CREATE INDEX IF NOT EXISTS idx_memory_metadata
    ON rag_agent_memory USING gin (metadata jsonb_path_ops);

-- 3.1 记忆召回函数：时间窗口 + 语义双路（对齐 PgVectorIndex.SQL_SEARCH_MEMORY_WINDOW）
CREATE OR REPLACE FUNCTION rag_recall_memory(
    p_embedding   vector(256),
    p_agent       TEXT        ,
    p_tenant      TEXT        DEFAULT 'default',
    p_window_from TIMESTAMPTZ DEFAULT now() - INTERVAL '30 days',
    p_window_to   TIMESTAMPTZ DEFAULT now(),
    p_top_k       INT         DEFAULT 5,
    p_min_sim     FLOAT8      DEFAULT 0.05
)
RETURNS TABLE (
    memory_id  BIGINT,
    agent_name TEXT,
    deal_id    TEXT,
    trace_id   TEXT,
    kind       TEXT,
    content    TEXT,
    similarity FLOAT8
)
LANGUAGE sql
STABLE
AS $$
    SELECT m.memory_id, m.agent_name, m.deal_id, m.trace_id, m.kind, m.content,
           1 - (m.embedding <=> p_embedding) AS similarity
    FROM rag_agent_memory m
    WHERE m.tenant_id = p_tenant
      AND m.agent_name = p_agent
      AND m.occurred_at >= p_window_from
      AND m.occurred_at <  p_window_to
      AND 1 - (m.embedding <=> p_embedding) >= p_min_sim
    ORDER BY m.embedding <=> p_embedding
    LIMIT GREATEST(p_top_k, 1);
$$;

COMMENT ON FUNCTION rag_recall_memory IS 'Agent 记忆召回：agent + 时间窗口 + 语义相似度（对齐 vector_rag.PgVectorIndex.SQL_SEARCH_MEMORY_WINDOW）';

-- -----------------------------------------------------------------------------
-- 4. 审计视图（只读，不含 embedding 大列，供 rag_auditor 角色使用）
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW rag_chunk_audit AS
SELECT chunk_id, tenant_id, collection, ref_id, chunk_no, title,
       source, created_at, updated_at
FROM rag_knowledge_chunk;

GRANT SELECT ON rag_chunk_audit TO PUBLIC;

-- -----------------------------------------------------------------------------
-- 5. 权限边界（最小权限；应用账号无 DDL / 无 TRUNCATE / 无 DELETE）
--    密钥管理：连接串经环境变量 POLARDB_PGVECTOR_DSN 注入，不落库不进代码
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_app') THEN
        CREATE ROLE rag_app NOLOGIN;          -- 应用服务角色（由具体登录角色继承）
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_auditor') THEN
        CREATE ROLE rag_auditor NOLOGIN;      -- 审计只读角色
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO rag_app, rag_auditor;
GRANT SELECT, INSERT, UPDATE ON rag_knowledge_chunk TO rag_app;   -- 无 DELETE：append-only + upsert 幂等
GRANT SELECT, INSERT ON rag_agent_memory TO rag_app;
GRANT SELECT ON rag_chunk_audit TO rag_auditor;
GRANT EXECUTE ON FUNCTION rag_search_chunks(vector(256), TEXT, TEXT, INT, FLOAT8, TIMESTAMPTZ, TIMESTAMPTZ) TO rag_app;
GRANT EXECUTE ON FUNCTION rag_recall_memory(vector(256), TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, INT, FLOAT8) TO rag_app;

REVOKE ALL ON rag_knowledge_chunk FROM PUBLIC;
REVOKE ALL ON rag_agent_memory FROM PUBLIC;

-- -----------------------------------------------------------------------------
-- 6. 回滚脚本（幂等；切换期保留旧 TF-IDF/JSONL 通道，回滚只停双写切回旧读路径）
-- -----------------------------------------------------------------------------
-- ROLLBACK 步骤（按序执行）：
-- REVOKE ALL ON FUNCTION rag_search_chunks(vector(256), TEXT, TEXT, INT, FLOAT8, TIMESTAMPTZ, TIMESTAMPTZ) FROM rag_app;
-- REVOKE ALL ON FUNCTION rag_recall_memory(vector(256), TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, INT, FLOAT8) FROM rag_app;
-- DROP FUNCTION IF EXISTS rag_search_chunks(vector(256), TEXT, TEXT, INT, FLOAT8, TIMESTAMPTZ, TIMESTAMPTZ);
-- DROP FUNCTION IF EXISTS rag_recall_memory(vector(256), TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, INT, FLOAT8);
-- DROP VIEW    IF EXISTS rag_chunk_audit;
-- DROP TABLE   IF EXISTS rag_agent_memory;
-- DROP TABLE   IF EXISTS rag_knowledge_chunk;
-- 数据保留策略：回滚前先 pg_dump 两表（含 embedding），审计要求保留 rag_agent_memory ≥ 180 天。

COMMIT;
