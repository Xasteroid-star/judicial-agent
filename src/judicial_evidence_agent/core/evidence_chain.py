"""Evidence chain analysis — RAG + LLM 驱动的证据链分析。

流程：
1. 检索：从 Chroma 召回相关法条 + 案件证据 chunk
2. 排序：法条按日期倒序（新法优先），案件按距离升序
3. 组装 prompt：法条上下文 + 证据上下文 → 结构化分析
4. LLM 生成：证据链报告（带溯源引用）
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder

from judicial_evidence_agent.core.llm import LLMClient, StubLLM

# 证据链分析系统提示词
EVIDENCE_CHAIN_SYSTEM_PROMPT = """你是一位司法证据链分析专家，负责审查刑事案件中的证据材料。
你的任务是基于提供的法条和证据片段，进行证据链分析。

核心规则：
1. 所有结论必须绑定来源（法条条文编号或证据材料ID）
2. 不得编造卷宗中不存在的事实
3. 证据充分性分为三级：确实充分 / 基本充分需补证 / 证据不足
4. 标注每条证据链的置信度（0-1）
5. 识别证据间的冲突和补强关系

输出格式：结构化 Markdown，包含：
- 案件证据概况
- 核心证据链（每条链列出：待证事实 → 支撑证据 → 法律依据 → 置信度）
- 证据冲突与风险点
- 补证建议
- 来源清单"""


class EvidenceChainAnalyzer:
    """RAG 证据链分析器。

    用法:
        analyzer = EvidenceChainAnalyzer()
        report = await analyzer.analyze("案卷材料中银行转账记录显示...")
    """

    # BGE 中文模型全局单例 — 首次加载后缓存，避免每次请求重新加载
    _model_cache = None
    _index_cache = None
    _metadata_cache = None
    _bm25_cache = None          # BM25 索引
    _bm25_corpus_cache = None   # BM25 语料（用于 reranker 候选文本）
    _reranker_cache = None      # BGE Reranker 模型

    def __init__(self, use_stub: bool = False):
        from judicial_evidence_agent.core.config import settings

        # 全局缓存：BGE 模型只加载一次
        if EvidenceChainAnalyzer._model_cache is None:
            import os
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            EvidenceChainAnalyzer._model_cache = SentenceTransformer(
                "BAAI/bge-small-zh-v1.5", device="cpu", local_files_only=True
            )
            self._index_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "bge_index"
            if self._index_dir.exists():
                EvidenceChainAnalyzer._index_cache = np.load(str(self._index_dir / "embeddings.npy"))
                EvidenceChainAnalyzer._metadata_cache = json.loads(
                    (self._index_dir / "metadata.json").read_text("utf-8")
                )
            else:
                EvidenceChainAnalyzer._index_cache = None
                EvidenceChainAnalyzer._metadata_cache = []

        self._model = EvidenceChainAnalyzer._model_cache
        self._embeddings = EvidenceChainAnalyzer._index_cache
        self._metadata = EvidenceChainAnalyzer._metadata_cache

        # ── BM25 索引 + Reranker 全局单例 ──
        if EvidenceChainAnalyzer._bm25_cache is None and self._metadata:
            EvidenceChainAnalyzer._bm25_cache = self._build_bm25_index(self._metadata)
            EvidenceChainAnalyzer._bm25_corpus_cache = [m.get("content", "") for m in self._metadata]

        # Reranker 改为懒加载（不阻塞启动，首次 _rerank() 调用时才加载）

        # LLM 客户端
        if use_stub:
            self._llm = StubLLM()
        else:
            self._llm = LLMClient(model=settings.anthropic_model)

    @staticmethod
    def _build_bm25_index(metadata: list[dict]):
        """构建 BM25 关键词索引。"""
        from rank_bm25 import BM25Okapi
        import jieba

        # 用 jieba 分词构建语料
        corpus = []
        for m in metadata:
            tokens = list(jieba.cut(m.get("content", "")[:500]))
            corpus.append(tokens)
        return BM25Okapi(corpus)

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        case_id: str = "",
        exclude_ids=None,
    ) -> list[dict]:
        """Fusion RAG：BGE 向量 + BM25 双路召回 → RRF 融合 → Reranker 精排。

        Args:
            exclude_ids: 排除已见过的 chunk_id 列表（人工驳回重检索时使用）。
        """
        if self._embeddings is None or not self._metadata:
            return []

        exclude_set = set(exclude_ids or [])

        # ═══════════════════════════════════════════════════════════════
        # 路 1: BGE 向量语义检索（召回 top_k * 3）
        # ═══════════════════════════════════════════════════════════════
        vector_results = self._vector_retrieve(query, top_k * 3, case_id, exclude_set)

        # ═══════════════════════════════════════════════════════════════
        # 路 2: BM25 关键词检索（召回 top_k * 3）
        # ═══════════════════════════════════════════════════════════════
        bm25_results = self._bm25_retrieve(query, top_k * 3, exclude_set)

        # ═══════════════════════════════════════════════════════════════
        # 路 3: RRF 融合去重
        # ═══════════════════════════════════════════════════════════════
        merged = self._rrf_fuse(vector_results, bm25_results, k=60)

        # ═══════════════════════════════════════════════════════════════
        # 路 4: Reranker 精排（取 RRF top 15 送入 Reranker）
        # ═══════════════════════════════════════════════════════════════
        candidates = merged[:15]
        if EvidenceChainAnalyzer._reranker_cache is not None and len(candidates) > 1:
            reranked = self._rerank(query, candidates)
        else:
            reranked = candidates  # Reranker 不可用时降级为 RRF 结果

        # ── 最终排序：法条按日期倒序 + 去重 ──
        statutes = sorted(
            [h for h in reranked if h.get("effective_date")],
            key=lambda h: h["effective_date"], reverse=True,
        )
        cases = [h for h in reranked if not h.get("effective_date")]

        seen = set()
        deduped = []
        for s in statutes:
            key = s["content"][:80]
            if key not in seen:
                seen.add(key)
                deduped.append(s)
        for c in cases:
            key = c["content"][:80]
            if key not in seen:
                seen.add(key)
                deduped.append(c)

        return deduped[:top_k]

    # ═══════════════════════════════════════════════════════════════════
    # Fusion RAG 子方法
    # ═══════════════════════════════════════════════════════════════════

    def _vector_retrieve(
        self, query: str, top_n: int, case_id: str, exclude_set: set
    ) -> list[dict]:
        """BGE 向量检索。"""
        q_emb = self._model.encode([query], show_progress_bar=False)[0]
        q_norm = q_emb / np.linalg.norm(q_emb)
        e_norm = self._embeddings / np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        similarities = np.dot(e_norm, q_norm)

        top_indices = np.argsort(similarities)[::-1]
        results = []
        for idx in top_indices:
            meta = self._metadata[idx]
            if meta["chunk_id"] in exclude_set:
                continue
            if not case_id or meta.get("effective_date") or meta.get("case_id") == case_id:
                results.append(dict(meta,
                    vector_score=float(similarities[idx]),
                    distance=round(float(1.0 - similarities[idx]), 4)))
            if len(results) >= top_n:
                break
        return results

    def _bm25_retrieve(self, query: str, top_n: int, exclude_set: set) -> list[dict]:
        """BM25 关键词检索（jieba 分词）。"""
        if EvidenceChainAnalyzer._bm25_cache is None:
            return []

        import jieba
        tokens = list(jieba.cut(query))
        scores = EvidenceChainAnalyzer._bm25_cache.get_scores(tokens)

        # 取 top_n，排除已见
        indices = np.argsort(scores)[::-1]
        results = []
        for idx in indices:
            meta = self._metadata[idx]
            if meta["chunk_id"] in exclude_set:
                continue
            results.append(dict(meta,
                bm25_score=float(scores[idx]),
                distance=round(float(1.0 / (1.0 + abs(scores[idx]))), 4)))
            if len(results) >= top_n:
                break
        return results

    @staticmethod
    def _rrf_fuse(*result_lists: list[dict], k: int = 60) -> list[dict]:
        """Reciprocal Rank Fusion — 多路结果融合。

        公式: score(d) = Σ 1 / (k + rank_i(d))
        """
        scores: dict[str, float] = {}       # chunk_id → rrf_score
        meta_map: dict[str, dict] = {}      # chunk_id → meta

        for results in result_lists:
            for rank, item in enumerate(results):
                cid = item["chunk_id"]
                if cid not in meta_map:
                    meta_map[cid] = item
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)

        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        result = []
        for cid, s in sorted_items:
            item = dict(meta_map[cid])
            item["distance"] = round(1.0 / (1.0 + s), 4)  # RRF → distance 转换
            item["rrf_score"] = round(s, 4)
            result.append(item)
        return result

    @staticmethod
    def _get_reranker():
        """懒加载 Reranker — 首次调用时下载（~300MB）。"""
        if EvidenceChainAnalyzer._reranker_cache is None:
            try:
                import os
                os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
                EvidenceChainAnalyzer._reranker_cache = CrossEncoder(
                    "BAAI/bge-reranker-base",
                    device="cpu",
                )
            except Exception:
                EvidenceChainAnalyzer._reranker_cache = False  # 标记为不可用
        return EvidenceChainAnalyzer._reranker_cache if EvidenceChainAnalyzer._reranker_cache is not False else None

    def _rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """BGE Reranker 精排 — 对候选文档逐对打分。"""
        reranker = self._get_reranker()
        if reranker is None:
            return candidates  # 降级

        pairs = [(query, c.get("content", "")[:500]) for c in candidates]
        scores = reranker.predict(pairs)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = round(float(s), 4)

        return sorted(candidates, key=lambda c: c.get("rerank_score", 0), reverse=True)

    @staticmethod
    def build_context(chunks: list[dict]) -> str:
        """构建用于 LLM 的上下文文本。"""
        parts = []
        statutes = [c for c in chunks if c["source_type"] == "statute"]
        evidence = [c for c in chunks if c["source_type"] == "case"]

        if statutes:
            parts.append("## 相关法条\n")
            for i, c in enumerate(statutes, 1):
                date = c["effective_date"][:10]
                parts.append(
                    f"[法条{i}] {c.get('law_name', '')} ({date})\n{c['content'][:800]}\n"
                )

        if evidence:
            parts.append("## 案件证据材料\n")
            for i, c in enumerate(evidence, 1):
                parts.append(
                    f"[证据{i}] 类型={c['evidence_type']} 案件={c['case_id'][:8]}\n"
                    f"{c['content'][:600]}\n"
                )

        return "\n".join(parts)

    async def analyze(
        self,
        query: str,
        case_context: str = "",
    ) -> dict:
        """执行证据链分析。

        Args:
            query: 分析问题
            case_context: 可选的案件背景描述

        Returns:
            {
                "query": str,
                "retrieved_chunks": list[dict],
                "analysis": str,  # LLM 生成的证据链分析报告
            }
        """
        # 1. 检索
        chunks = self.retrieve(query)
        context = self.build_context(chunks)

        # 2. 组装 prompt
        user_prompt = f"""## 案件背景
{case_context or '（由用户查询提供）'}

## 分析请求
{query}

## 可用材料
{context}

请基于以上材料进行证据链分析。如果材料不足以得出结论，请明确说明需要补充哪些证据。"""

        # 3. LLM 生成
        try:
            analysis = await self._llm.generate(
                prompt=user_prompt,
                system=EVIDENCE_CHAIN_SYSTEM_PROMPT,
                max_tokens=2048,
            )
        except Exception as e:
            analysis = f"[LLM 调用失败: {e}]"

        return {
            "query": query,
            "retrieved_chunks": [
                {
                    "chunk_id": c["chunk_id"],
                    "source_type": c["source_type"],
                    "effective_date": c.get("effective_date", ""),
                    "content_preview": c["content"][:120],
                    "distance": c["distance"],
                }
                for c in chunks
            ],
            "analysis": analysis,
        }
