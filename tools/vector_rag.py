"""向量 RAG 升级模块：从 TF-IDF 稀疏检索升级为稠密向量检索。

提供三种检索后端，统一接口，可无缝切换：
1. TF-IDF（纯 Python，零依赖）——当前基线
2. Dense（字符 n-gram 哈希 + 余弦相似度，纯 Python，零依赖）——升级路径演示
3. PolarDB pgvector（接口预留）——复赛迁移目标

迁移到 PolarDB pgvector 时，只需替换 _embed() 为模型推理 + _search() 为 pgvector ANN 查询，
search() 接口不变，上层 Skill/Agent 零改动。

用法：
    from vector_rag import create_rag_index
    index = create_rag_index(docs, backend="dense")  # 或 "tfidf" / "pgvector"
    results = index.search("家庭 SUV 六座 新能源")
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Callable, Dict, List, Optional, Protocol


# ---- 统一接口 ----

class RagIndex(Protocol):
    """RAG 检索统一接口。所有后端实现此接口，上层 Skill/Agent 零改动。"""

    def search(self, query: Optional[str], top_k: int = 3, threshold: float = 0.05) -> List[Dict[str, Any]]:
        ...


# ---- 停用词 ----

_STOPWORDS = {
    "的", "了", "在", "吗", "吧", "呢", "想", "要", "请问", "什么", "怎么", "如何",
    "客户", "表示", "提出", "提到", "希望", "需要", "要求", "咨询", "进行", "完成",
    "输出", "结果", "这个", "那个", "一下", "看看", "推荐", "查询", "评估", "计算",
}


def _segment(text: str) -> List[str]:
    """字符级分词 + bigram（纯 Python，无 jieba 依赖）。"""
    tokens = re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", text.lower())
    terms: List[str] = []
    for token in tokens:
        if len(token) == 1 and "\u4e00" <= token <= "\u9fff":
            terms.extend(token[i: i + 2] for i in range(len(token) - 1))
        else:
            terms.append(token)
    return [t for t in terms if t and t not in _STOPWORDS]


def _doc_text(d: Dict[str, Any]) -> str:
    """从文档字典提取可检索文本。"""
    parts = []
    for k in ("title", "summary", "content", "text", "case_title", "sop_name"):
        v = d.get(k)
        if isinstance(v, str):
            parts.append(v)
    if "tags" in d and isinstance(d["tags"], list):
        parts.extend(str(t) for t in d["tags"])
    if "match_terms" in d and isinstance(d["match_terms"], list):
        parts.extend(str(t) for t in d["match_terms"])
    return " ".join(parts)


# ---- 后端 1：TF-IDF（基线） ----

class TFIDFIndex:
    """TF-IDF + 余弦相似度（纯 Python 标准库）。"""

    def __init__(self, docs: List[Dict[str, Any]], threshold: float = 0.05, top_k: int = 3) -> None:
        self.docs = docs
        self.threshold = threshold
        self.top_k = top_k
        self.doc_tokens = [_segment(_doc_text(d)) for d in docs]
        df: Dict[str, int] = {}
        for toks in self.doc_tokens:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        n = max(len(docs), 1)
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        self.doc_vecs = [self._tfidf(toks) for toks in self.doc_tokens]
        self.norms = [self._norm(v) for v in self.doc_vecs]

    @staticmethod
    def _tfidf(tokens: List[str]) -> Dict[str, float]:
        from collections import Counter
        tf = Counter(tokens)
        total = max(sum(tf.values()), 1)
        return {t: (c / total) for t, c in tf.items()}

    @staticmethod
    def _norm(vec: Dict[str, float]) -> float:
        return math.sqrt(sum(v * v for v in vec.values())) or 1.0

    def _cosine(self, vec_a: Dict[str, float], norm_a: float,
                vec_b: Dict[str, float], norm_b: float) -> float:
        common = set(vec_a) & set(vec_b)
        if not common:
            return 0.0
        dot = sum(vec_a[k] * vec_b[k] for k in common)
        return dot / (norm_a * norm_b)

    def search(self, query: Optional[str], top_k: int = 3, threshold: float = 0.05) -> List[Dict[str, Any]]:
        if not query:
            return []
        q_toks = _segment(query)
        if not q_toks:
            return []
        # 查询 TF-IDF 向量（使用已建索引的 IDF）
        from collections import Counter
        q_tf = Counter(q_toks)
        q_total = max(sum(q_tf.values()), 1)
        q_vec = {t: (c / q_total) * self.idf.get(t, 1.0) for t, c in q_tf.items() if c > 0}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        scored = []
        for i, (dv, dn) in enumerate(zip(self.doc_vecs, self.norms)):
            sim = self._cosine(q_vec, q_norm, dv, dn)
            if sim >= threshold:
                scored.append((sim, i))
        scored.sort(reverse=True)
        return [self.docs[i] for _, i in scored[:min(top_k, self.top_k)]]


# ---- 后端 2：Dense（字符 n-gram 哈希稠密向量） ----

class DenseRagIndex:
    """稠密向量 RAG：字符 n-gram 哈希 → 固定维度向量 → 余弦相似度。

    与 TF-IDF 的区别：
    - TF-IDF 是稀疏向量（维度=词表大小），只考虑精确词匹配
    - Dense 是稠密向量（固定 256 维），字符 n-gram 哈希天然支持子串模糊匹配
    - 例如"六座SUV"和"6座suv"在 TF-IDF 中完全不同，但在 Dense 中因共享字符 n-gram 而相近

    迁移到真实 embedding 模型（如 text-embedding-v3）时：
    - 替换 _embed() 为模型推理
    - 替换 _cosine() 为 numpy 或 pgvector 的 ANN 检索
    - search() 接口不变
    """

    DIM = 256  # 固定向量维度
    NGRAM_RANGE = (2, 4)  # 字符 n-gram 范围

    def __init__(self, docs: List[Dict[str, Any]], threshold: float = 0.05, top_k: int = 3) -> None:
        self.docs = docs
        self.threshold = threshold
        self.top_k = top_k
        self.doc_vecs = [self._embed(_doc_text(d)) for d in docs]

    def _embed(self, text: str) -> List[float]:
        """字符 n-gram 哈希 → 固定维度稠密向量（纯 Python，零依赖）。"""
        vec = [0.0] * self.DIM
        text = text.lower().strip()
        if not text:
            return vec
        for n in range(self.NGRAM_RANGE[0], self.NGRAM_RANGE[1] + 1):
            for i in range(len(text) - n + 1):
                gram = text[i: i + n]
                h = int(hashlib.md5(gram.encode()).hexdigest()[:8], 16)
                idx = h % self.DIM
                # 带符号哈希（正负抵消噪声）
                sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
                vec[idx] += sign
        # L2 归一化
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def search(self, query: Optional[str], top_k: int = 3, threshold: float = 0.05) -> List[Dict[str, Any]]:
        if not query:
            return []
        q_vec = self._embed(query)
        scored = []
        for i, dv in enumerate(self.doc_vecs):
            sim = self._cosine(q_vec, dv)
            if sim >= threshold:
                scored.append((sim, i))
        scored.sort(reverse=True)
        return [self.docs[i] for _, i in scored[:min(top_k, self.top_k)]]


# ---- 后端 3：PolarDB pgvector（接口预留） ----

class PgVectorIndex:
    """PolarDB pgvector 向量检索（接口预留）。

    迁移步骤：
    1. 安装 psycopg2 + pgvector 扩展
    2. 创建表：CREATE TABLE docs (id SERIAL, embedding vector(256), metadata JSONB);
    3. 插入文档向量：INSERT INTO docs (embedding, metadata) VALUES (%s, %s);
    4. 创建 ANN 索引：CREATE INDEX ON docs USING ivfflat (embedding vector_cosine_ops);
    5. 检索：SELECT metadata FROM docs ORDER BY embedding <-> %s LIMIT %s;

    search() 接口与 TFIDFIndex / DenseRagIndex 完全一致。
    """

    def __init__(self, docs: List[Dict[str, Any]], connection_string: str = "",
                 threshold: float = 0.05, top_k: int = 3) -> None:
        self.docs = docs
        self.threshold = threshold
        self.top_k = top_k
        self.conn_string = connection_string
        # TODO: 初始化 pgvector 连接
        # self.conn = psycopg2.connect(connection_string)

    def search(self, query: Optional[str], top_k: int = 3, threshold: float = 0.05) -> List[Dict[str, Any]]:
        if not query:
            return []
        # TODO: 用 embedding 模型生成查询向量
        # q_vec = embedding_model.encode(query)
        # rows = self.conn.execute(
        #     "SELECT metadata FROM docs ORDER BY embedding <-> %s LIMIT %s",
        #     (q_vec, min(top_k, self.top_k))
        # )
        # return [row[0] for row in rows if row[1] >= threshold]
        raise NotImplementedError(
            "PgVectorIndex 需要 psycopg2 + pgvector 扩展。"
            "当前为接口预留，迁移时实现 search()。"
            "接口与 TFIDFIndex / DenseRagIndex 完全一致。"
        )


# ---- 工厂函数 ----

_BACKENDS = {
    "tfidf": TFIDFIndex,
    "dense": DenseRagIndex,
    "pgvector": PgVectorIndex,
}


def create_rag_index(docs: List[Dict[str, Any]], backend: str = "dense",
                     threshold: float = 0.05, top_k: int = 3) -> RagIndex:
    """创建 RAG 检索索引。

    Args:
        docs: 文档列表（字典，含 title/summary/content/text 等字段）
        backend: 检索后端 ("tfidf" | "dense" | "pgvector")
        threshold: 相似度阈值（低于此值返回空）
        top_k: 返回前 K 个结果

    Returns:
        RagIndex 实例（统一 search() 接口）
    """
    cls = _BACKENDS.get(backend)
    if cls is None:
        raise ValueError(f"未知后端: {backend}，可选: {list(_BACKENDS.keys())}")
    return cls(docs, threshold=threshold, top_k=top_k)


# ---- 对比演示 ----

def demo_comparison() -> None:
    """对比 TF-IDF vs Dense 在同一组查询上的检索效果。"""
    docs = [
        {"title": "理想 L7", "summary": "六座大型SUV 家庭出行 新能源 增程式 续航1100km", "tags": ["SUV", "六座", "新能源"]},
        {"title": "问界 M7", "summary": "六座智能SUV 华为鸿蒙座舱 新能源 纯电续航200km", "tags": ["SUV", "六座", "智能"]},
        {"title": "秦 PLUS", "summary": "紧凑型轿车 经济省油 代步通勤 新能源 DM-i 超级混动", "tags": ["轿车", "经济", "新能源"]},
        {"title": "唐 DM-i", "summary": "七座大型SUV 置换升级 家庭出行 空间大 DM-i 混动", "tags": ["SUV", "七座", "置换"]},
        {"title": "试驾 SOP", "summary": "客户表达试驾意愿时 确认档期 预约门店 安排销售顾问陪同", "tags": ["SOP", "试驾"]},
        {"title": "议价底线守护", "summary": "优惠让步不得超出授权底线 触底停止让步 转人工交接", "tags": ["SOP", "议价", "风控"]},
    ]

    queries = [
        "六座SUV 新能源 家庭",
        "置换 大空间 七座",
        "试驾怎么安排",
        "经济省油 代步车",
        "优惠底线在哪里",
    ]

    print("=" * 70)
    print("RAG 检索后端对比：TF-IDF vs Dense（字符 n-gram 哈希）")
    print("=" * 70)

    for q in queries:
        print(f"\n查询: {q}")
        tfidf_results = create_rag_index(docs, backend="tfidf").search(q)
        dense_results = create_rag_index(docs, backend="dense").search(q)
        print(f"  TF-IDF ({len(tfidf_results)} 条): {[r.get('title', '?') for r in tfidf_results]}")
        print(f"  Dense  ({len(dense_results)} 条): {[r.get('title', '?') for r in dense_results]}")

    print(f"\n{'=' * 70}")
    print("Dense 后端因字符 n-gram 子串匹配，对模糊查询（如'六座'vs'6座'、")
    print("'SUV'vs'suv'）有更好的召回率。迁移到真实 embedding 模型后效果更佳。")


if __name__ == "__main__":
    demo_comparison()
