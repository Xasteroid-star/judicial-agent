"""Tests for RAG fusion pipeline — RRF, build_context, and NumpyRetriever.

覆盖：
- RRF 融合算法正确性（纯数学，不依赖外部服务）
- build_context 格式化（纯字符串，不依赖外部服务）
- NumpyRetriever 接口契约（需要 bge_index）
"""

import pytest

# ── RRF 融合测试 ──────────────────────────────────────────────────────


class TestRRFFusion:
    """Reciprocal Rank Fusion 正确性测试。

    RRF 公式: score(d) = Σ 1 / (k + rank_i(d))
    其中 k=60, rank 从 0 开始。
    """

    @staticmethod
    def _make_chunk(cid: str, source_type: str = "case", **kwargs) -> dict:
        """快速构造测试用 chunk。"""
        return {"chunk_id": cid, "content": f"content-{cid}", "source_type": source_type, **kwargs}

    def test_single_list_returns_same_order(self):
        """单路结果 → RRF 保持原序。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        chunks = [
            self._make_chunk("a"),
            self._make_chunk("b"),
            self._make_chunk("c"),
        ]
        result = EvidenceChainAnalyzer._rrf_fuse(chunks, k=60)
        assert [c["chunk_id"] for c in result] == ["a", "b", "c"]

    def test_two_lists_merge_by_reciprocal_rank(self):
        """双路融合 — 在两路都排第一的 chunk 获胜。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        list_a = [
            self._make_chunk("shared"),
            self._make_chunk("only_a"),
        ]
        list_b = [
            self._make_chunk("shared"),
            self._make_chunk("only_b"),
        ]
        result = EvidenceChainAnalyzer._rrf_fuse(list_a, list_b, k=60)

        # shared 在两路都排第一，RRF 分数最高
        assert result[0]["chunk_id"] == "shared"
        # 后面两个各有一次排名第二
        assert len(result) == 3
        assert set(c["chunk_id"] for c in result) == {"shared", "only_a", "only_b"}

    def test_rank_matters_more_than_source(self):
        """排名靠前的 chunk 即使只在一路出现，也能胜过两路都靠后的。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        list_a = [
            self._make_chunk("top_in_a"),   # rank 0
            self._make_chunk("mid"),        # rank 1
        ]
        list_b = [
            self._make_chunk("bottom"),     # rank 0
            self._make_chunk("mid"),        # rank 1
        ]
        result = EvidenceChainAnalyzer._rrf_fuse(list_a, list_b, k=60)

        # top_in_a: 1/61 ≈ 0.0164
        # mid: 1/62 + 1/62 ≈ 0.0323  → mid wins!
        # bottom: 1/61 ≈ 0.0164
        assert result[0]["chunk_id"] == "mid"

    def test_rrf_score_computation(self):
        """验证 RRF 分数计算的数值精度。

        rrf_score 被 round(s, 4) 截断，所以用 round() 做精确比较。
        """
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        chunks = [self._make_chunk("x"), self._make_chunk("y")]
        result = EvidenceChainAnalyzer._rrf_fuse(chunks, k=60)

        # x 在 rank 0 → rrf = round(1/61, 4) = 0.0164
        assert result[0]["rrf_score"] == round(1.0 / 61, 4)
        # y 在 rank 1 → rrf = round(1/62, 4) = 0.0161
        assert result[1]["rrf_score"] == round(1.0 / 62, 4)

    def test_empty_input(self):
        """空输入 → 返回空列表。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        result = EvidenceChainAnalyzer._rrf_fuse([], k=60)
        assert result == []

    def test_custom_k_value(self):
        """k 值越大排名差异越小，k 越小越强调排名。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        chunks = [self._make_chunk("a"), self._make_chunk("b")]

        # k=1 → 排名影响很大
        r1 = EvidenceChainAnalyzer._rrf_fuse(chunks, k=1)
        # k=100 → 排名影响很小
        r100 = EvidenceChainAnalyzer._rrf_fuse(chunks, k=100)

        # k=1 时分数差异更大
        diff_1 = r1[0]["rrf_score"] - r1[1]["rrf_score"]
        diff_100 = r100[0]["rrf_score"] - r100[1]["rrf_score"]
        assert diff_1 > diff_100

    def test_preserves_metadata(self):
        """RRF 融合保留原始 chunk 的 metadata 字段。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        chunks = [
            self._make_chunk("a", evidence_type="物证", effective_date="2023-01-01"),
            self._make_chunk("b", law_name="刑法", effective_date=""),
        ]
        result = EvidenceChainAnalyzer._rrf_fuse(chunks, k=60)

        assert result[0]["evidence_type"] == "物证"
        assert result[1]["law_name"] == "刑法"
        # RRF 融合后会新增 distance 和 rrf_score 字段
        assert "rrf_score" in result[0]
        assert "distance" in result[0]


# ── build_context 测试 ─────────────────────────────────────────────────


class TestBuildContext:
    """build_context 格式化测试。"""

    def test_statutes_and_evidence_separated(self):
        """法规和证据分段输出。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        chunks = [
            {
                "chunk_id": "s1",
                "source_type": "statute",
                "law_name": "刑法",
                "effective_date": "2024-01-01T00:00:00",
                "content": "第264条 盗窃罪...",
            },
            {
                "chunk_id": "e1",
                "source_type": "case",
                "case_id": "CASE-001-XXXX",
                "evidence_type": "物证",
                "content": "银行转账记录显示...",
                "effective_date": "",
            },
        ]
        ctx = EvidenceChainAnalyzer.build_context(chunks)

        assert "## 相关法条" in ctx
        assert "## 案件证据材料" in ctx
        # 法条在前
        assert ctx.index("相关法条") < ctx.index("案件证据材料")

    def test_only_statutes(self):
        """仅有法条时不输出证据段。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        chunks = [
            {
                "chunk_id": "s1",
                "source_type": "statute",
                "law_name": "刑事诉讼法",
                "effective_date": "2023-06-01T00:00:00",
                "content": "第55条...",
            },
        ]
        ctx = EvidenceChainAnalyzer.build_context(chunks)

        assert "## 相关法条" in ctx
        assert "## 案件证据材料" not in ctx

    def test_only_evidence(self):
        """仅有证据时不输出法条段。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        chunks = [
            {
                "chunk_id": "e1",
                "source_type": "case",
                "case_id": "CASE-002",
                "evidence_type": "书证",
                "content": "合同文本...",
                "effective_date": "",
            },
        ]
        ctx = EvidenceChainAnalyzer.build_context(chunks)

        assert "相关法条" not in ctx
        assert "## 案件证据材料" in ctx

    def test_empty_chunks(self):
        """空列表返回空字符串。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        ctx = EvidenceChainAnalyzer.build_context([])
        assert ctx == ""

    def test_effective_date_truncated_to_10_chars(self):
        """生效日期截取前 10 位（YYYY-MM-DD）。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        chunks = [
            {
                "chunk_id": "s1",
                "source_type": "statute",
                "law_name": "刑法",
                "effective_date": "2024-01-01T00:00:00.000Z",
                "content": "test",
            },
        ]
        ctx = EvidenceChainAnalyzer.build_context(chunks)
        assert "2024-01-01" in ctx

    def test_content_truncated(self):
        """长内容被截断（法条 800 字、证据 600 字）。"""
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer

        # 用不同内容的字符段，确保截断断言有效
        long_content = "A" * 800 + "B" * 200  # 前 800 是 A，后面是 B
        chunks = [
            {
                "chunk_id": "s1",
                "source_type": "statute",
                "law_name": "刑法",
                "effective_date": "2024-01-01",
                "content": long_content,
            },
        ]
        ctx = EvidenceChainAnalyzer.build_context(chunks)
        # 法条内容最多 800 字 → 只有 A，没有 B
        assert "A" * 100 in ctx
        assert "B" not in ctx


# ── NumpyRetriever 接口契约测试 ────────────────────────────────────────


class TestNumpyRetrieverInterface:
    """NumpyRetriever 实现 RetrievalInterface 契约。"""

    @pytest.fixture
    def retriever(self):
        from judicial_evidence_agent.core.retrieval import NumpyRetriever
        return NumpyRetriever()

    @pytest.mark.asyncio
    async def test_search_returns_list(self, retriever):
        """search() 返回 list[dict]。"""
        results = await retriever.search("盗窃罪", top_k=5)
        assert isinstance(results, list)
        if results:
            assert "chunk_id" in results[0]
            assert "content" in results[0]
            assert "distance" in results[0]

    @pytest.mark.asyncio
    async def test_keyword_search_returns_list(self, retriever):
        """keyword_search() 返回 list[dict]。"""
        results = await retriever.keyword_search("盗窃", top_k=5)
        assert isinstance(results, list)
        if results:
            assert "bm25_score" in results[0]

    @pytest.mark.asyncio
    async def test_hybrid_search_returns_list(self, retriever):
        """hybrid_search() 返回 list[dict]。"""
        results = await retriever.hybrid_search("盗窃罪", top_k=5)
        assert isinstance(results, list)
        if results:
            assert "chunk_id" in results[0]
            assert "distance" in results[0]

    @pytest.mark.asyncio
    async def test_search_respects_top_k(self, retriever):
        """search() 遵守 top_k 限制。"""
        results = await retriever.search("证据", top_k=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_search_with_case_id_filter(self, retriever):
        """search() 支持 case_id 过滤。"""
        results = await retriever.search("证据", case_id="NONEXISTENT-CASE-ID")
        # 不存在的 case_id 应返回法规结果（法规不受 case_id 过滤）
        if results:
            assert all(
                r.get("source_type") == "statute" or r.get("case_id") == "NONEXISTENT-CASE-ID"
                for r in results
            )

    @pytest.mark.asyncio
    async def test_min_score_filter(self, retriever):
        """search() 按 min_score 过滤低相关性结果。"""
        # min_score=0.99 几乎不返回任何结果
        strict = await retriever.search("盗窃罪", top_k=10, min_score=0.99)
        # min_score=0.0 返回所有结果
        loose = await retriever.search("盗窃罪", top_k=10, min_score=0.0)

        assert len(strict) <= len(loose) if loose else True

    @pytest.mark.asyncio
    async def test_index_chunk_warns_not_supported(self, retriever, caplog):
        """index_chunk() 记录警告日志。"""
        import logging
        with caplog.at_level(logging.WARNING):
            await retriever.index_chunk("test-1", "content", {"type": "case"})

        assert "增量索引" in caplog.text or "NumpyRetriever" in caplog.text

    @pytest.mark.asyncio
    async def test_delete_by_case_returns_minus_one(self, retriever):
        """delete_by_case() 返回 -1（不支持）。"""
        result = await retriever.delete_by_case("CASE-001")
        assert result == -1


# ── 工厂函数测试 ──────────────────────────────────────────────────────


class TestGetRetriever:
    """get_retriever() 工厂函数测试。"""

    def test_returns_singleton(self):
        """多次调用返回同一实例。"""
        from judicial_evidence_agent.core.retrieval import get_retriever

        r1 = get_retriever()
        r2 = get_retriever()
        assert r1 is r2

    def test_returns_numpy_retriever_by_default(self):
        """默认返回 NumpyRetriever。"""
        from judicial_evidence_agent.core.retrieval import get_retriever, NumpyRetriever

        r = get_retriever()
        assert isinstance(r, NumpyRetriever)


# ── 综合测试：完整 Fusion RAG 管线 ────────────────────────────────────


class TestFusionPipeline:
    """端到端融合管线测试（需要 bge_index 就绪）。"""

    @pytest.fixture
    def analyzer(self):
        from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer
        return EvidenceChainAnalyzer(use_stub=False)

    def test_retrieve_returns_chunks(self, analyzer):
        """基本 smoke test: retrieve() 返回结果。"""
        results = analyzer.retrieve("盗窃罪的构成要件", top_k=5)
        assert isinstance(results, list)

    def test_retrieve_respects_top_k(self, analyzer):
        """retrieve() 遵守 top_k 限制。"""
        results = analyzer.retrieve("证据", top_k=3)
        assert len(results) <= 3

    def test_retrieve_results_sorted_statutes_first(self, analyzer):
        """返回结果中法条排在前面。"""
        results = analyzer.retrieve("违法", top_k=10)
        if not results:
            pytest.skip("索引为空，跳过排序测试")

        # 找到第一个 case chunk 的位置
        statute_count = sum(1 for r in results if r.get("source_type") == "statute")
        if statute_count > 0 and statute_count < len(results):
            # 前 statute_count 个应该全是 statute
            for i in range(statute_count):
                assert results[i].get("source_type") == "statute", (
                    f"前 {statute_count} 个应为 statute，但第 {i} 个是 {results[i].get('source_type')}"
                )

    def test_retrieve_deduplicates_content(self, analyzer):
        """retrieve() 返回结果无重复内容（前 80 字符去重）。"""
        results = analyzer.retrieve("法律", top_k=10)
        if not results:
            pytest.skip("索引为空，跳过去重测试")

        prefixes = [r["content"][:80] for r in results]
        assert len(prefixes) == len(set(prefixes)), "检索结果存在重复内容"

    def test_retrieve_with_exclude_ids(self, analyzer):
        """retrieve() 尊重 exclude_ids 排除列表。"""
        # 先做一次检索获取 chunk_id
        results_all = analyzer.retrieve("盗窃罪", top_k=5)
        if len(results_all) < 2:
            pytest.skip("索引结果不足，跳过排除测试")

        excluded_id = results_all[0]["chunk_id"]
        results_excluded = analyzer.retrieve(
            "盗窃罪", top_k=5, exclude_ids=[excluded_id]
        )

        excluded_ids_in_result = {r["chunk_id"] for r in results_excluded}
        assert excluded_id not in excluded_ids_in_result, (
            f"excluded_id {excluded_id} 仍出现在结果中"
        )

    def test_vector_retrieve_scores_in_range(self, analyzer):
        """向量检索的 vector_score 在合理范围内。"""
        results = analyzer._vector_retrieve("盗窃罪", top_n=10, case_id="", exclude_set=set())
        for r in results:
            assert -1.0 <= r["vector_score"] <= 1.0, (
                f"vector_score={r['vector_score']} 超出范围 [-1, 1]"
            )
            assert r["distance"] >= 0, f"distance={r['distance']} 应为非负数"

    def test_bm25_retrieve_scores(self, analyzer):
        """BM25 检索返回非空的 bm25_score。"""
        results = analyzer._bm25_retrieve("盗窃罪 非法占有", top_n=5, exclude_set=set())
        if results:
            for r in results:
                assert "bm25_score" in r
                assert isinstance(r["bm25_score"], float)

    @pytest.mark.slow
    def test_rerank_preserves_order(self, analyzer):
        """Reranker 精排后结果仍按分数降序。"""
        # 先获取候选
        candidates = analyzer.retrieve("故意伤害罪", top_k=5)
        if len(candidates) < 3:
            pytest.skip("候选不足，跳过 reranker 测试")

        reranked = analyzer._rerank("故意伤害罪", candidates)
        if reranked is candidates:
            pytest.skip("Reranker 不可用（未加载或加载失败），跳过")

        scores = [r.get("rerank_score", 0) for r in reranked]
        assert scores == sorted(scores, reverse=True), "Reranker 结果未按分数降序排列"
