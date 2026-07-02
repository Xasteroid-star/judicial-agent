"""RAG retrieval — 检索增强生成接口。

对向量库的统一检索接口，底层可换 Chroma / pgvector / Milvus / numpy。
参考 architecture.md §5.4 和 Patchwork-Assurance Seam 2。

所有检索走此接口，API 和 eval harness 调用同一路径。
"""

from __future__ import annotations

import logging
from typing import Optional

from judicial_evidence_agent.core.config import settings

logger = logging.getLogger(__name__)


class RetrievalInterface:
    """检索接口 — 薄包装，底层可换 Chroma / pgvector / Milvus / numpy。

    所有检索走此接口，API 和 eval harness 调用同一路径。
    """

    async def search(
        self,
        query: str,
        case_id: Optional[str] = None,
        modality: Optional[str] = None,
        top_k: int = 10,
        min_score: float = 0.3,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """语义检索，返回最相关证据片段。

        可选过滤：案件ID、材料类型、时间范围、法律要件。
        """
        raise NotImplementedError

    async def keyword_search(
        self,
        query: str,
        case_id: Optional[str] = None,
        top_k: int = 20,
    ) -> list[dict]:
        """关键词检索，用于精确匹配（人名、案号、金额等）。"""
        raise NotImplementedError

    async def hybrid_search(
        self,
        query: str,
        case_id: Optional[str] = None,
        top_k: int = 10,
        vector_weight: float = 0.7,
    ) -> list[dict]:
        """混合检索：向量 + 关键词，加权融合结果。"""
        raise NotImplementedError

    async def index_chunk(
        self,
        chunk_id: str,
        content: str,
        metadata: dict,
    ) -> None:
        """索引一条证据片段。"""
        raise NotImplementedError

    async def delete_by_case(self, case_id: str) -> int:
        """删除某个案件的所有索引。"""
        raise NotImplementedError


class NumpyRetriever(RetrievalInterface):
    """基于 numpy + JSON 的检索实现。

    包装 EvidenceChainAnalyzer 的 Fusion RAG 管线：
    BGE 向量 + BM25 双路召回 → RRF 融合 → BGE Reranker 精排。

    适用场景：本地开发、离线环境（无需 Chroma/pgvector 服务）。
    限制：不支持增量索引，新增/删除需通过 build_vector_index.py 重建。
    """

    def __init__(self):
        # 延迟导入避免循环依赖
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        self._analyzer = EvidenceChainAnalyzer(use_stub=False)

    # ── RetrievalInterface 实现 ──────────────────────────────────────────

    async def search(
        self,
        query: str,
        case_id: Optional[str] = None,
        modality: Optional[str] = None,
        top_k: int = 10,
        min_score: float = 0.3,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """语义检索 — 走完整 Fusion RAG 管线。

        返回距离 ≤ (1 - min_score) 的结果（距离越小越相关）。
        """
        results = self._analyzer.retrieve(
            query, top_k=max(top_k, 30), case_id=case_id or ""
        )
        return [r for r in results if r.get("distance", 1.0) <= (1.0 - min_score)][:top_k]

    async def keyword_search(
        self,
        query: str,
        case_id: Optional[str] = None,
        top_k: int = 20,
    ) -> list[dict]:
        """纯 BM25 关键词检索（jieba 分词）。"""
        exclude_set = set()
        return self._analyzer._bm25_retrieve(query, top_k, exclude_set)

    async def hybrid_search(
        self,
        query: str,
        case_id: Optional[str] = None,
        top_k: int = 10,
        vector_weight: float = 0.7,
    ) -> list[dict]:
        """混合检索 — 直接走 Fusion RAG 全管线（已含 RRF 融合）。

        Note:
            vector_weight 参数当前未使用，Fusion RAG 的 RRF
            本身已平衡双路权重。如需精确控制权重，
            可改为加权线性融合替代 RRF。
        """
        return self._analyzer.retrieve(
            query, top_k=top_k, case_id=case_id or ""
        )

    async def index_chunk(
        self,
        chunk_id: str,
        content: str,
        metadata: dict,
    ) -> None:
        """增量索引 — numpy 方案不支持。

        numpy 索引是静态的，新增 chunk 需通过
        scripts/build_vector_index.py 全量重建。
        """
        logger.warning(
            "NumpyRetriever 不支持增量索引（chunk_id=%s），"
            "请使用 scripts/build_vector_index.py 重建索引。",
            chunk_id,
        )

    async def delete_by_case(self, case_id: str) -> int:
        """按案件删除 — numpy 方案不支持。

        返回 -1 表示不支持此操作，调用方应检查返回值。
        """
        logger.warning(
            "NumpyRetriever 不支持按案件删除（case_id=%s），"
            "请使用 scripts/build_vector_index.py 重建索引。",
            case_id,
        )
        return -1


# ── 工厂函数 ──────────────────────────────────────────────────────────

_retriever: Optional[NumpyRetriever] = None


def get_retriever() -> RetrievalInterface:
    """获取当前配置的检索器实例（单例）。

    根据 settings.vector_backend 返回对应实现：
    - "numpy" / default → NumpyRetriever
    - 未来可扩展 "chroma" / "pgvector" / "milvus"
    """
    global _retriever
    if _retriever is None:
        backend = getattr(settings, "vector_backend", "numpy")
        if backend == "numpy":
            _retriever = NumpyRetriever()
        else:
            logger.warning(
                "未知的 vector_backend '%s'，回退到 NumpyRetriever", backend
            )
            _retriever = NumpyRetriever()
    return _retriever
