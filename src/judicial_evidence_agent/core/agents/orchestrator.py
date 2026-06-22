"""Agent 编排器 — LangGraph 流水线。

architecture.md §7 定义的 8 个 Agent 按以下顺序执行：

  卷宗解析 → 要素抽取 → RAG检索 → 知识图谱 → 证据链分析
                                                     ↓
                                               置信度审查
                                                     ↓
                                                报告生成
                                                     ↓
                                                人工复核

所有 Agent 调用通过 LangSmith @traceable 上报 tracing。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Optional

# load_dotenv() 必须先于 langsmith import，确保 LANGCHAIN_* 环境变量就绪
from judicial_evidence_agent.core.config import settings  # noqa: F401

from langsmith import traceable

from judicial_evidence_agent.core.agents.base import AgentContext
from judicial_evidence_agent.core.agents.docket_parser import DocketParserAgent
from judicial_evidence_agent.core.agents.element_extractor import ElementExtractorAgent
from judicial_evidence_agent.core.agents.rag_retriever import RAGRetrieverAgent
from judicial_evidence_agent.core.agents.knowledge_graph import KnowledgeGraphAgent
from judicial_evidence_agent.core.agents.evidence_chain import EvidenceChainAgent
from judicial_evidence_agent.core.agents.confidence_reviewer import ConfidenceReviewerAgent
from judicial_evidence_agent.core.agents.report_generator import ReportGeneratorAgent
from judicial_evidence_agent.core.agents.human_review import HumanReviewAgent


class AgentPipeline:
    """证据链分析流水线 — 8 个 Agent，其中要素抽取 + RAG 检索并行执行。

    执行顺序:
      卷宗解析 ──┬── 要素抽取 ──┬── 知识图谱 ── 证据链分析 ── 置信度审查 ── 报告生成 ── 人工复核
                 └── RAG 检索 ──┘

    用法:
        pipeline = AgentPipeline()
        result = await pipeline.run(
            case_id="1",
            case_name="王某故意伤害案",
            query="证据链是否完整？",
            case_context="..."
        )
    """

    def __init__(self, stub_llm: bool = False):
        from judicial_evidence_agent.core.llm import LLMClient, StubLLM

        self._stub = stub_llm
        llm = StubLLM() if stub_llm else LLMClient()

        self._docket_parser = DocketParserAgent()
        self._element_extractor = ElementExtractorAgent(llm_client=llm)
        self._rag_retriever = RAGRetrieverAgent()
        self._knowledge_graph = KnowledgeGraphAgent(llm_client=llm)
        self._evidence_chain = EvidenceChainAgent(llm_client=llm)
        self._confidence_reviewer = ConfidenceReviewerAgent()
        self._report_generator = ReportGeneratorAgent(llm_client=llm)
        self._human_review = HumanReviewAgent()

    @traceable(run_type="chain", name="AgentPipeline.run")
    async def run(
        self,
        case_id: str = "",
        case_name: str = "",
        query: str = "",
        case_context: str = "",
    ) -> dict:
        """执行流水线：卷宗解析后，要素抽取和 RAG 检索并行。"""
        from judicial_evidence_agent.core.guardrails import MAX_RETRY_COUNT

        ctx = AgentContext(
            case_id=case_id,
            case_name=case_name,
            query=query,
            case_context=case_context,
        )

        prev_ctx_hash = None
        stall_count = 0

        def _check_stall():
            nonlocal prev_ctx_hash, stall_count
            current_hash = hash(str(ctx.extracted_elements) + str(ctx.evidence_chains))
            if current_hash == prev_ctx_hash:
                stall_count += 1
            else:
                stall_count = 0
            prev_ctx_hash = current_hash
            return stall_count >= MAX_RETRY_COUNT

        # Phase 1: 卷宗解析（必须先完成）
        ctx = await self._docket_parser.run(ctx)
        if _check_stall():
            return self._serialize(ctx)

        # Phase 2: 要素抽取 + RAG 检索并行（互不依赖）
        ctx_element, ctx_rag = await asyncio.gather(
            self._element_extractor.run(ctx),
            self._rag_retriever.run(ctx),
        )
        # 合并：要素结果来自 element_extractor，检索结果来自 rag_retriever
        ctx.extracted_elements = ctx_element.extracted_elements
        ctx.retrieved_statutes = ctx_rag.retrieved_statutes
        ctx.retrieved_chunks = ctx_rag.retrieved_chunks
        if _check_stall():
            return self._serialize(ctx)

        # Phase 3-8: 串行（后续 Agent 依赖前面全部产出）
        for agent in [
            self._knowledge_graph,
            self._evidence_chain,
            self._confidence_reviewer,
            self._report_generator,
            self._human_review,
        ]:
            ctx = await agent.run(ctx)
            if _check_stall():
                break

        return self._serialize(ctx)

    @staticmethod
    def _serialize(ctx: AgentContext) -> dict:
        """序列化上下文为 API 响应格式。"""
        return {
            "case_id": ctx.case_id,
            "case_name": ctx.case_name,
            "processing": {
                "materials_parsed": len(ctx.material_ids),
                "elements_extracted": len(ctx.extracted_elements),
                "statutes_retrieved": len(ctx.retrieved_statutes),
                "evidence_chunks_retrieved": len(ctx.retrieved_chunks),
                "graph_nodes": len(ctx.graph_nodes),
                "graph_edges": len(ctx.graph_edges),
            },
            "extracted_elements": ctx.extracted_elements,
            "retrieved_statutes": [
                {
                    "chunk_id": s["chunk_id"],
                    "effective_date": s.get("effective_date", ""),
                    "content_preview": s["content"][:100],
                    "evidence_type": s.get("evidence_type", ""),
                    "distance": s["distance"],
                }
                for s in ctx.retrieved_statutes
            ],
            "retrieved_chunks": [
                {
                    "chunk_id": c["chunk_id"],
                    "content_preview": c["content"][:120],
                    "evidence_type": c.get("evidence_type", ""),
                    "source_type": "case",
                    "distance": c["distance"],
                }
                for c in ctx.retrieved_chunks
            ],
            "graph": {
                "nodes": ctx.graph_nodes,
                "edges": ctx.graph_edges,
            },
            "evidence_chains": [
                {
                    "chain_id": c["chain_id"],
                    "fact_to_prove": c["fact_to_prove"],
                    "confidence": c["confidence"],
                    "status": c["status"],
                    "supporting_evidence_count": len(c["supporting_evidence"]),
                    "missing_evidence_count": len(c["missing_evidence"]),
                }
                for c in ctx.evidence_chains
            ],
            "confidence": {
                "dimensions": ctx.confidence_dimensions,
                "final": ctx.final_confidence,
                "threshold_result": ctx.threshold_result,
            },
            "report": {
                "title": ctx.report_title,
                "sections": ctx.report_sections,
                "markdown": ctx.report_markdown,
            },
            "review": {
                "status": ctx.review_status,
                "items": ctx.review_items,
            },
        }
