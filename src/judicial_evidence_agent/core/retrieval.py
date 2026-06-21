"""RAG retrieval — 检索增强生成接口。

对向量库的统一检索接口，包装 Chroma（本地开发）或 pgvector（生产）。
参考 architecture.md §5.4 和 Patchwork-Assurance Seam 2。
"""

from typing import Optional

from judicial_evidence_agent.core.config import settings


class RetrievalInterface:
    """检索接口 — 薄包装，底层可换 Chroma / pgvector / Milvus。

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
