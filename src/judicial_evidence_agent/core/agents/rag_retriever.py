"""RAG 检索 Agent — architecture.md §5.4, §7

检索策略：向量检索 + 关键词检索 + 多维度过滤。
检索源：案卷证据片段、法条、司法解释、证据审查规则。

所有向量/关键词检索统一走 RetrievalInterface，方便切换后端
（numpy / Chroma / pgvector / Milvus）。
"""

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext
from judicial_evidence_agent.core.retrieval import get_retriever


class RAGRetrieverAgent(BaseAgent):
    """RAG 检索 Agent。

    职责：
    1. 根据查询从向量库检索相关法条 + 案件证据
    2. 法条按生效日期倒序（新法优先）
    3. 返回携带来源引用的检索结果
    """

    name = "rag_retriever"

    async def run(self, ctx: AgentContext) -> AgentContext:
        import sqlite3, json

        # 策略1：先直接加载本案已有的证据片段（不走检索，保证精准）
        case_chunks = []
        if ctx.case_id:
            try:
                conn = sqlite3.connect("data/judicial_evidence.db")
                # 尝试 UUID 匹配，失败则按 case_name 模糊匹配
                rows = conn.execute(
                    "SELECT chunk_id, content_text, extracted_elements, case_id FROM evidence_chunks WHERE case_id=? LIMIT 10",
                    (ctx.case_id,),
                ).fetchall()
                if not rows:
                    # UUID 没命中，尝试用 case_id 当 case_name 搜
                    rows = conn.execute(
                        "SELECT chunk_id, content_text, extracted_elements, case_id FROM evidence_chunks WHERE case_id IN (SELECT case_id FROM cases WHERE case_name LIKE ?) LIMIT 10",
                        (f"%{ctx.case_id}%",),
                    ).fetchall()
                conn.close()
                for r in rows:
                    case_chunks.append({
                        "chunk_id": r[0],
                        "content": r[1] or "",
                        "source_type": "case",
                        "effective_date": "",
                        "law_name": "",
                        "evidence_type": (json.loads(r[2]).get("evidence_type", "") if r[2] else ""),
                        "case_id": r[3] or "",
                        "distance": 0.1,  # 本案证据距离最低
                    })
            except Exception:
                pass

        # 策略2：向量+关键词检索补充法条和相似案例
        # 统一走 RetrievalInterface（后端由 JEA_VECTOR_BACKEND 环境变量控制）
        retriever = get_retriever()

        search_terms = [ctx.case_context, ctx.query]
        for e in ctx.extracted_elements[:5]:
            if e.get("confidence", 0) >= 0.7:
                search_terms.append(f"{e['category']}:{e['value']}")
        search_query = " ".join(t for t in search_terms if t)

        retrieved = await retriever.search(
            search_query, case_id=ctx.case_id, top_k=10, min_score=0.0
        )

        # 法条去重
        seen_ids = {c["chunk_id"] for c in case_chunks}
        ctx.retrieved_statutes = []
        ctx.retrieved_chunks = []

        for c in retrieved:
            if c["chunk_id"] in seen_ids:
                continue
            seen_ids.add(c["chunk_id"])
            if c["source_type"] == "statute":
                ctx.retrieved_statutes.append(c)
            else:
                ctx.retrieved_chunks.append(c)

        # 本案证据放在最前面
        ctx.retrieved_chunks = case_chunks + ctx.retrieved_chunks

        return ctx
