"""Evidence chain analysis — RAG + LLM 驱动的证据链分析。

流程：
1. 检索：从 Chroma 召回相关法条 + 案件证据 chunk
2. 排序：法条按日期倒序（新法优先），案件按距离升序
3. 组装 prompt：法条上下文 + 证据上下文 → 结构化分析
4. LLM 生成：证据链报告（带溯源引用）
"""

from __future__ import annotations

import re

from chromadb import PersistentClient
from chromadb.utils import embedding_functions

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

    def __init__(self, use_stub: bool = False):
        # Chroma
        from judicial_evidence_agent.core.config import settings

        # TODO: 网络可达 huggingface.co 后，替换下行即可
        # self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        #     model_name="BAAI/bge-small-zh-v1.5", device="cpu")
        # 当前使用内置英文模型，中文语义匹配精度有限
        self._ef = embedding_functions.DefaultEmbeddingFunction()
        from pathlib import Path

        chroma_path = Path(settings.chroma_persist_dir)
        if not chroma_path.is_absolute():
            chroma_path = Path(__file__).resolve().parent.parent.parent.parent / chroma_path
        self._chroma = PersistentClient(path=str(chroma_path))
        self._collection = self._chroma.get_collection(
            "judicial_evidence_chunks", embedding_function=self._ef
        )

        # LLM
        if use_stub:
            self._llm = StubLLM()
        else:
            from judicial_evidence_agent.core.config import settings

            self._llm = LLMClient(model=settings.anthropic_model)

    def retrieve(self, query: str, top_k: int = 10, case_id: str = "") -> list[dict]:
        """混合检索：向量 + 关键词。向量召回语义相关，关键词保证精准命中。

        双通道策略（防止跨案件污染）：
        - 法条（effective_date 有值）：不限案件，全局检索
        - 案件证据：若 case_id 提供则严格限定本案，否则全局检索
        """
        # ── 通道1：不限 case_id 的向量检索（获取法条） ──
        all_hits = []
        stat_hits = self._vector_search(query, top_k * 2, case_id_filter="")
        for h in stat_hits:
            if h["effective_date"]:  # 法条总是保留
                all_hits.append(h)

        # ── 通道2：限定/不限 case_id 的案件证据向量检索 ──
        ev_hits = self._vector_search(query, top_k * 2, case_id_filter=case_id)
        for h in ev_hits:
            if not h["effective_date"]:  # 只保留案件证据（可能被 case_id 过滤）
                all_hits.append(h)

        # ── 通道3：关键词全文检索 ──
        keywords = [w for w in re.findall(r"[一-鿿]{2,6}", query) if len(w) >= 2]
        crime_match = re.findall(r"(?:犯? |构成)?([一-鿿]{2,6})(?:罪)", query)
        crime_keywords = [f"{c}罪" for c in crime_match]
        keywords = crime_keywords + keywords

        seen_ids = {h["chunk_id"] for h in all_hits}
        if keywords:
            try:
                for kw in keywords[:5]:
                    try:
                        # 法条关键词不限 case_id
                        kw_results = self._collection.get(
                            where_document={"$contains": kw}, limit=6,
                        )
                    except Exception:
                        continue
                    if kw_results and kw_results.get("ids"):
                        for i, kid in enumerate(kw_results["ids"]):
                            if kid in seen_ids:
                                continue
                            seen_ids.add(kid)
                            meta = kw_results["metadatas"][i] if i < len(kw_results.get("metadatas", [])) else {}
                            if not case_id or meta.get("effective_date") or meta.get("case_id") == case_id:
                                # 法条无限制；证据只收本案
                                doc = kw_results["documents"][i] if i < len(kw_results.get("documents", [])) else ""
                                all_hits.append({
                                    "chunk_id": kid, "content": doc,
                                    "source_type": meta.get("source_type", "case"),
                                    "effective_date": meta.get("effective_date", ""),
                                    "law_name": meta.get("law_name", ""),
                                    "evidence_type": meta.get("evidence_type", ""),
                                    "case_id": meta.get("case_id", ""),
                                    "distance": 0.25,
                                })
            except Exception:
                pass

        # ── 排序：法条按日期倒序，案件证据按距离升序 ──
        statutes = sorted(
            [h for h in all_hits if h["effective_date"]],
            key=lambda h: h["effective_date"], reverse=True,
        )
        cases = sorted(
            [h for h in all_hits if not h["effective_date"]],
            key=lambda h: h["distance"],
        )

        # 去重
        seen = set()
        deduped_statutes = []
        for s in statutes:
            key = s["content"][:80]
            if key not in seen:
                seen.add(key)
                deduped_statutes.append(s)
        seen_cases = set()
        deduped_cases = []
        for c in cases:
            key = c["content"][:80]
            if key not in seen_cases:
                seen_cases.add(key)
                deduped_cases.append(c)

        return deduped_statutes[:top_k // 2] + deduped_cases[:top_k // 2]

    def _vector_search(self, query: str, n_results: int, case_id_filter: str) -> list[dict]:
        """向量检索内部方法。case_id_filter 为空字符串表示不限案件。"""
        kwargs = dict(query_texts=[query], n_results=n_results)
        if case_id_filter:
            kwargs["where"] = {"case_id": case_id_filter}
        results = self._collection.query(**kwargs)
        hits = []
        if not results or not results.get("ids") or not results["ids"][0]:
            return hits
        for doc_id, doc, meta, dist in zip(
            results["ids"][0], results["documents"][0],
            results["metadatas"][0], results["distances"][0],
        ):
            hits.append({
                "chunk_id": doc_id, "content": doc,
                "source_type": meta.get("source_type", "case"),
                "effective_date": meta.get("effective_date", ""),
                "law_name": meta.get("law_name", ""),
                "evidence_type": meta.get("evidence_type", ""),
                "case_id": meta.get("case_id", ""),
                "distance": dist,
            })
        return hits

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
