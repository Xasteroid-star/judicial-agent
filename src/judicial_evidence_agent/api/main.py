"""FastAPI 应用入口 — 完整 API 层（对照 architecture.md §4 应用后端）。"""

from pathlib import Path

# load_dotenv() 必须先于 langsmith import，确保 LANGCHAIN_* 环境变量就绪
from judicial_evidence_agent.core.config import settings  # noqa: F401

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langsmith import traceable
from pydantic import BaseModel

app = FastAPI(
    title="司法多模态证据链 Agent",
    version="0.1.0",
    description="面向公检法场景的多模态证据链分析系统",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Schemas
# ============================================================================

class AnalyzeRequest(BaseModel):
    case_id: str = ""
    query: str
    case_context: str = ""
    mode: str = "llm"  # "llm" = 深度分析（慢）, "fast" = 规则引擎（秒出）


class MaterialCreate(BaseModel):
    case_id: str
    name: str
    type: str
    source_org: str = ""
    collector: str = ""
    confidentiality_level: str = "medium"


class ReviewAction(BaseModel):
    review_id: str
    action: str  # confirm / reject
    note: str = ""


# ============================================================================
# Health
# ============================================================================

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/debug/langsmith")
async def debug_langsmith():
    import os
    return {
        "LANGCHAIN_TRACING_V2": os.environ.get("LANGCHAIN_TRACING_V2", "NOT SET"),
        "LANGCHAIN_PROJECT": os.environ.get("LANGCHAIN_PROJECT", "NOT SET"),
    }


# ============================================================================
# 案件 API
# ============================================================================

@app.get("/api/cases")
async def list_cases():
    """案件列表（从 SQLite 加载）。"""
    import sqlite3
    conn = sqlite3.connect("data/judicial_evidence.db")
    rows = conn.execute(
        "SELECT case_id, case_name, case_number, case_type, charge, decision_type, created_at FROM cases ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    if not rows:
        return [{"case_id": "0", "case_name": "无案件数据", "case_number": "", "case_type": "", "created_at": ""}]
    return [
        {"case_id": r[0], "case_name": r[1], "case_number": r[2], "case_type": r[3],
         "charge": r[4] or "", "decision_type": r[5] or "", "created_at": r[6] or ""}
        for r in rows
    ]


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str):
    """案件详情（从 SQLite 加载）。"""
    import sqlite3, json
    conn = sqlite3.connect("data/judicial_evidence.db")
    row = conn.execute(
        "SELECT case_id, case_name, case_number, case_type, charge, description, source FROM cases WHERE case_id=?",
        (case_id,)
    ).fetchone()
    if not row:
        return {"case_id": case_id, "case_name": f"案件{case_id}", "case_number": "", "case_type": "", "fact": "未找到该案件"}

    # 加载证据列表
    ev_rows = conn.execute(
        "SELECT extracted_elements, content_text FROM evidence_chunks WHERE case_id=? LIMIT 10",
        (case_id,)
    ).fetchall()
    evidence_list = []
    for ev in ev_rows:
        try:
            meta = json.loads(ev[0]) if ev[0] else {}
            etype = meta.get("evidence_type", "证据")
        except Exception:
            etype = "证据"
        evidence_list.append({"type": etype, "name": (ev[1] or "")[:60]})

    conn.close()

    return {
        "case_id": row[0],
        "case_name": row[1],
        "case_number": row[2],
        "case_type": row[3],
        "charge": row[4] or "",
        "fact": row[5] or "",
        "source": row[6] or "",
        "evidence_list": evidence_list,
    }


# ============================================================================
# 材料 API (§5.1)
# ============================================================================

@app.get("/api/materials")
async def list_materials(case_id: str = ""):
    """卷宗材料列表 — 从数据库加载。"""
    import sqlite3
    conn = sqlite3.connect("data/judicial_evidence.db")
    if case_id:
        rows = conn.execute(
            "SELECT material_id, case_id, name, type, source_org, collector, confidentiality_level, file_hash, file_path, processing_status, created_at FROM materials WHERE case_id=? ORDER BY created_at DESC LIMIT 50",
            (case_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT material_id, case_id, name, type, source_org, collector, confidentiality_level, file_hash, file_path, processing_status, created_at FROM materials ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    conn.close()
    if not rows:
        return []
    return [
        {
            "material_id": r[0], "case_id": r[1], "name": r[2], "type": r[3],
            "source_org": r[4] or "", "collector": r[5] or "",
            "confidentiality_level": r[6] or "medium", "file_hash": r[7] or "",
            "file_path": r[8] or "", "processing_status": r[9] or "pending",
            "created_at": r[10] or "",
        }
        for r in rows
    ]


@app.post("/api/materials")
async def create_material(req: MaterialCreate):
    """登记新材料。"""
    import sqlite3
    conn = sqlite3.connect("data/judicial_evidence.db")
    conn.execute(
        "INSERT INTO materials (material_id, case_id, name, type, source_org, collector, confidentiality_level) VALUES (?,?,?,?,?,?,?)",
        (f"M-{hash(req.name) & 0xFFFF:04x}", req.case_id, req.name, req.type, req.source_org, req.collector, req.confidentiality_level),
    )
    conn.commit()
    conn.close()
    return {"status": "registered", **req.dict()}


# ============================================================================
# 证据片段 API (§5.2-5.3)
# ============================================================================

@app.get("/api/evidence-chunks")
async def list_chunks(case_id: str = ""):
    """证据片段列表 — 从数据库加载。"""
    import sqlite3, json
    conn = sqlite3.connect("data/judicial_evidence.db")
    if case_id:
        rows = conn.execute(
            "SELECT chunk_id, case_id, material_id, modality, content_text, extracted_elements, source_pointer, confidence, model_version, created_at FROM evidence_chunks WHERE case_id=? ORDER BY created_at DESC LIMIT 100",
            (case_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT chunk_id, case_id, material_id, modality, content_text, extracted_elements, source_pointer, confidence, model_version, created_at FROM evidence_chunks ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    conn.close()
    result = []
    for r in rows:
        try:
            elements = json.loads(r[5]) if r[5] else {}
        except Exception:
            elements = {}
        try:
            source = json.loads(r[6]) if r[6] else {}
        except Exception:
            source = {}
        result.append({
            "chunk_id": r[0], "case_id": r[1], "material_id": r[2],
            "modality": r[3], "content_text": r[4] or "",
            "extracted_elements": elements,
            "source_pointer": source,
            "confidence": r[7] or 0.0, "model_version": r[8] or "",
            "created_at": r[9] or "",
        })
    return result


# ============================================================================
# 图谱 API (§5.5)
# ============================================================================

@app.get("/api/graph")
@traceable(run_type="chain", name="API.get_graph")
async def get_graph(case_id: str = "", query: str = "", case_context: str = ""):
    """知识图谱数据 — 使用 LLM 驱动的 Agent 动态生成。"""
    from judicial_evidence_agent.core.agents.base import AgentContext
    from judicial_evidence_agent.core.agents.element_extractor import ElementExtractorAgent
    from judicial_evidence_agent.core.agents.knowledge_graph import KnowledgeGraphAgent
    from judicial_evidence_agent.core.llm import LLMClient

    ctx = AgentContext(
        case_id=case_id or "graph-req",
        query=query or "证据链图谱分析",
        case_context=case_context or "",
    )

    # 如果有 case_id，从数据库加载
    if case_id and case_context == "":
        import sqlite3, json
        conn = sqlite3.connect("data/judicial_evidence.db")
        row = conn.execute(
            "SELECT case_name, description FROM cases WHERE case_id=?",
            (case_id,)
        ).fetchone()
        if row:
            ctx.case_name = row[0] or ""
            ctx.case_context = row[1] or ""
        # 加载证据 chunks
        chunk_rows = conn.execute(
            "SELECT content_text, extracted_elements FROM evidence_chunks WHERE case_id=? LIMIT 10",
            (case_id,)
        ).fetchall()
        for cr in chunk_rows:
            try:
                elems = json.loads(cr[1]) if cr[1] else {}
            except Exception:
                elems = {}
            ctx.retrieved_chunks.append({
                "chunk_id": f"db-{len(ctx.retrieved_chunks)}",
                "content": cr[0] or "",
                "evidence_type": elems.get("evidence_type", ""),
                "distance": 0.1,
            })
        conn.close()

    llm = LLMClient()

    # 先提取要素
    extractor = ElementExtractorAgent(llm_client=llm)
    ctx = await extractor.run(ctx)

    # 再构建图谱
    graph_builder = KnowledgeGraphAgent(llm_client=llm)
    ctx = await graph_builder.run(ctx)

    return {
        "nodes": ctx.graph_nodes,
        "edges": ctx.graph_edges,
    }


# ============================================================================
# 证据链分析 API — RAG + LLM (§5.4, §5.7-5.8)
# ============================================================================

@app.post("/api/analyze")
@traceable(run_type="chain", name="API.analyze")
async def analyze(req: AnalyzeRequest):
    """证据链分析：8-Agent 流水线。

    mode=fast: 规则引擎，秒出结果（适合快速浏览）
    mode=llm:  DeepSeek 深度语义分析（默认，较慢但更准确）
    """
    from judicial_evidence_agent.core.agents.orchestrator import AgentPipeline

    use_stub = req.mode == "fast"
    pipeline = AgentPipeline(stub_llm=use_stub)
    result = await pipeline.run(
        case_id=req.case_id or "sample",
        case_name="案件",
        query=req.query,
        case_context=req.case_context,
    )
    return result


@app.get("/api/agent-status")
async def agent_status():
    """Agent 流水线架构信息。"""
    return {
        "agents": [
            {"name": "卷宗解析 Agent", "status": "active", "phase": 1},
            {"name": "要素抽取 Agent ∥ RAG检索 Agent", "status": "active", "phase": 2},
            {"name": "知识图谱 Agent", "status": "active", "phase": 3},
            {"name": "证据链分析 Agent", "status": "active", "phase": 4},
            {"name": "置信度审查 Agent", "status": "active", "phase": 5},
            {"name": "报告生成 Agent", "status": "active", "phase": 6},
            {"name": "人工复核 Agent", "status": "active", "phase": 7},
        ],
        "pipeline": "parallel (phase 2: extractor ∥ rag)",
        "orchestration": "LangGraph + asyncio.gather",
        "modes": ["fast (规则引擎, <1s)", "llm (DeepSeek深度分析, ~30s)"],
    }


# ============================================================================
# 报告 API (§5.8)
# ============================================================================

@app.get("/api/reports")
async def list_reports(case_id: str = ""):
    """报告列表 — 从已复核完成的案件生成。"""
    import sqlite3, json

    conn = sqlite3.connect("data/judicial_evidence.db")
    where = "WHERE review_status IN ('confirmed','rejected','needs_supplement')"
    params = ()
    if case_id:
        where += " AND case_id=?"
        params = (case_id,)

    rows = conn.execute(
        f"SELECT case_id, case_name, review_status, judgment_key, case_summary, charges, core_disputes "
        f"FROM annotated_cases {where} ORDER BY case_name LIMIT 50",
        params,
    ).fetchall()

    reports = []
    for r in rows:
        cid, name, status, judgment, summary, charges_json, disputes_json = r
        try:
            charges = json.loads(charges_json) if charges_json else []
            disputes = json.loads(disputes_json) if disputes_json else []
        except Exception:
            charges, disputes = [], []

        reports.append({
            "report_id": cid,
            "case_id": cid,
            "title": f"{name} — 证据链审查报告",
            "status": status,
            "judgment": judgment or "",
            "charges": charges,
            "disputes": disputes,
            "summary": (summary or "")[:200],
            "created_at": "",
        })

    conn.close()

    if not reports:
        return [{
            "report_id": "",
            "case_id": case_id or "",
            "title": "暂无已完成的审查报告",
            "status": "empty",
            "judgment": "",
            "charges": [],
            "disputes": [],
            "summary": "",
            "created_at": "",
        }]
    return reports


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str):
    """单份报告详情。"""
    import sqlite3, json

    conn = sqlite3.connect("data/judicial_evidence.db")
    row = conn.execute(
        """SELECT a.case_id, a.case_name, a.review_status, a.judgment_key,
                  a.case_summary, a.charges, a.core_disputes, a.evidence_types,
                  a.applicable_articles, a.retry_count,
                  c.description, c.charge, c.article
           FROM annotated_cases a
           LEFT JOIN cases c ON a.case_id = c.case_id
           WHERE a.case_id=?""",
        (report_id,),
    ).fetchone()

    if not row:
        conn.close()
        return {"error": "报告不存在", "report_id": report_id}

    # 加载关联证据
    ev_rows = conn.execute(
        "SELECT content_text, extracted_elements, modality FROM evidence_chunks WHERE case_id=? LIMIT 15",
        (report_id,),
    ).fetchall()
    evidence = []
    for ev in ev_rows:
        try:
            meta = json.loads(ev[1]) if ev[1] else {}
            etype = meta.get("evidence_type", "")
        except Exception:
            etype = ""
        evidence.append({
            "content": (ev[0] or "")[:300],
            "type": etype or ev[2] or "",
        })

    # 加载审计日志（复核历史）
    audit_rows = conn.execute(
        "SELECT timestamp, action, detail FROM audit_logs WHERE target_id=? ORDER BY timestamp ASC",
        (report_id,),
    ).fetchall()
    review_history = []
    for ar in audit_rows:
        try:
            d = json.loads(ar[2]) if ar[2] else {}
        except Exception:
            d = {}
        review_history.append({
            "timestamp": ar[0],
            "action": ar[1],
            "note": d.get("note", ""),
            "new_confidence": d.get("new_confidence"),
        })

    conn.close()

    try:
        charges = json.loads(row[5]) if row[5] else []
        disputes = json.loads(row[6]) if row[6] else []
        evidence_types = json.loads(row[7]) if row[7] else []
        articles = json.loads(row[8]) if row[8] else []
    except Exception:
        charges, disputes, evidence_types, articles = [], [], [], []

    return {
        "report_id": row[0],
        "case_name": row[1],
        "status": row[2],
        "judgment": row[3] or "",
        "summary": row[4] or row[10] or "",
        "charges": charges or ([row[11]] if row[11] else []),
        "disputes": disputes,
        "evidence_types": evidence_types,
        "articles": articles or ([row[12]] if row[12] else []),
        "retry_count": row[9] or 0,
        "evidence": evidence,
        "review_history": review_history,
    }


# ============================================================================
# 复核 API (§5.7)
# ============================================================================

@app.get("/api/reviews")
async def list_reviews(case_id: str = ""):
    """复核项列表（从标注库加载，置信度基于多维标注完整度动态计算）。"""
    import sqlite3, json
    conn = sqlite3.connect("data/judicial_evidence.db")
    try:
        rows = conn.execute(
            """SELECT a.case_id, a.case_name, a.core_disputes, a.charges,
                      a.case_summary, a.evidence_types, a.applicable_articles,
                      COALESCE(a.retry_count, 0) as retry_count
               FROM annotated_cases a
               WHERE a.review_status='pending' AND a.case_id != '_init_' AND a.case_name != '_init_'
               LIMIT 50"""
        ).fetchall()
        if rows:
            items = []
            for r in rows:
                try:
                    disputes = json.loads(r[2]) if r[2] else []
                    charges = json.loads(r[3]) if r[3] else []
                    evidence_types = json.loads(r[5]) if r[5] else []
                    articles = json.loads(r[6]) if r[6] else []
                except Exception:
                    disputes, charges, evidence_types, articles = [], [], [], []

                # ── 回退充实：从 cases 表 + evidence_chunks 补齐缺失字段 ──
                summary = r[4] or ""

                if not charges:
                    # 从 cases 表取 charge 字段
                    case_row = conn.execute(
                        "SELECT charge FROM cases WHERE case_id=?", (r[0],)
                    ).fetchone()
                    if case_row and case_row[0]:
                        charges = [case_row[0]]

                if not disputes:
                    # 从 evidence_chunks 文本做关键词规则提取
                    chunk_row = conn.execute(
                        "SELECT content_text FROM evidence_chunks WHERE case_id=? LIMIT 3",
                        (r[0],)
                    ).fetchall()
                    chunk_text = " ".join(c[0] for c in chunk_row if c[0])
                    if chunk_text:
                        disputes = _extract_disputes_heuristic(chunk_text)

                if not summary:
                    # 从 cases.description 或 evidence_chunks 取文本
                    case_row = conn.execute(
                        "SELECT description FROM cases WHERE case_id=?", (r[0],)
                    ).fetchone()
                    if case_row and case_row[0]:
                        summary = case_row[0]
                    else:
                        chunk_row = conn.execute(
                            "SELECT content_text FROM evidence_chunks WHERE case_id=? LIMIT 1",
                            (r[0],)
                        ).fetchone()
                        if chunk_row and chunk_row[0]:
                            summary = chunk_row[0][:100]

                if not evidence_types:
                    # 从 evidence_chunks 的 extracted_elements 推断
                    chunk_rows = conn.execute(
                        "SELECT extracted_elements FROM evidence_chunks WHERE case_id=? LIMIT 10",
                        (r[0],)
                    ).fetchall()
                    for cr in chunk_rows:
                        try:
                            elems = json.loads(cr[0]) if cr[0] else {}
                            etype = elems.get("evidence_type", "")
                            if etype and etype not in evidence_types:
                                evidence_types.append(etype)
                        except Exception:
                            pass

                # ── 多维置信度计算 ──
                # 维度1: 争议点 — 每个争议点 0.25，2个封顶
                dispute_score = min(len(disputes) * 0.25, 0.50)
                # 维度2: 罪名 — 每个罪名 0.15，2个封顶
                charge_score = min(len(charges) * 0.15, 0.30)
                # 维度3: 证据类型 — 每种 0.08，2种封顶
                evidence_score = min(len(evidence_types) * 0.08, 0.16)
                # 维度4: 适用法条 — 每条 0.05，2条封顶
                article_score = min(len(articles) * 0.05, 0.10)
                # 维度5: 摘要完整度
                summary_len = len(summary)
                if summary_len > 80:
                    summary_score = 0.14
                elif summary_len > 30:
                    summary_score = 0.10
                else:
                    summary_score = 0.04

                confidence = round(
                    0.30                       # 基线（案件已入库的基本可信度）
                    + dispute_score            # 0 ~ 0.50
                    + charge_score             # 0 ~ 0.30
                    + evidence_score           # 0 ~ 0.16
                    + article_score            # 0 ~ 0.10
                    + summary_score,           # 0.04 ~ 0.14
                    2
                )
                confidence = min(confidence, 1.00)  # 封顶

                # ── 详情文本 ──
                detail_parts = []
                detail_parts.append(f"争议点: {', '.join(disputes) if disputes else '待确认'} ({len(disputes)}个)")
                detail_parts.append(f"罪名: {', '.join(charges) if charges else '待确认'} ({len(charges)}个)")
                if evidence_types:
                    detail_parts.append(f"证据类型: {', '.join(evidence_types[:3])} ({len(evidence_types)}种)")
                if articles:
                    detail_parts.append(f"适用法条: {', '.join(articles[:3])} ({len(articles)}条)")
                if summary:
                    detail_parts.append(f"摘要: {summary[:120]}")

                items.append({
                    "id": r[0], "type": "evidence", "title": r[1],
                    "detail": "\n".join(detail_parts),
                    "confidence": confidence, "status": "pending",
                    "retry_count": r[7] if len(r) > 7 else 0,
                })
            conn.close()
            return items
    except Exception:
        pass
    conn.close()
    return [
        {"id": "RV-001", "type": "evidence", "title": "证人证言可信度审查", "confidence": 0.78, "status": "pending"},
        {"id": "RV-002", "type": "edge", "title": "证明关系审查", "confidence": 0.82, "status": "pending"},
    ]


def _extract_disputes_heuristic(text: str) -> list[str]:
    """规则启发式从案件文本提取争议点（作为 LLM 标注缺失时的回退）。"""
    disputes = []
    kw_map = [
        (["刑讯", "逼供", "非法取证", "非法证据"], "非法取证/刑讯逼供"),
        (["证据不足", "无法认定", "不能认定", "存疑"], "证据不足认定"),
        (["自首", "自动投案", "如实供述", "投案"], "自首认定"),
        (["正当防卫", "防卫过当"], "正当防卫"),
        (["主犯", "从犯", "胁从犯", "共犯"], "主从犯认定"),
        (["立功", "重大立功"], "立功认定"),
        (["谅解", "和解", "赔偿"], "被害人谅解"),
        (["未遂", "既遂", "中止"], "犯罪形态认定"),
        (["数额", "金额认定", "价值"], "涉案金额认定"),
        (["精神病", "行为能力", "刑事责任能力"], "刑事责任能力"),
        (["明知", "应知", "故意", "过失", "主观"], "主观故意认定"),
        (["管辖", "移送", "并案"], "管辖权争议"),
        (["时效", "追诉时效", "诉讼时效"], "追诉时效"),
        (["鉴定", "鉴定意见", "结论异议"], "鉴定意见争议"),
        (["翻供", "口供反复", "供述不一致"], "供述一致性"),
    ]
    for keywords, label in kw_map:
        if any(kw in text for kw in keywords):
            disputes.append(label)
    return disputes[:3]  # 最多3个


@app.post("/api/reviews/{review_id}")
async def submit_review(review_id: str, req: ReviewAction):
    """提交复核结果：确认直接通过；驳回触发检索重跑（最多3轮）。"""
    import sqlite3, json, uuid
    from datetime import datetime, timezone

    conn = sqlite3.connect("data/judicial_evidence.db")

    # ── 0. 确保扩展表/字段存在 ──
    _ensure_schema(conn)

    # ── 1. 映射 action → 状态 ──
    action_map = {
        "confirm": "confirmed", "确认": "confirmed",
        "reject":  "rejected",  "驳回": "rejected",
    }
    new_status = action_map.get(req.action, req.action)

    # ── 2. 确认：直接通过 ──
    if new_status == "confirmed":
        judgment = f"人工确认: {req.note}" if req.note else "人工确认"
        conn.execute(
            "UPDATE annotated_cases SET review_status=?, judgment_key=?, retry_count=0 WHERE case_id=?",
            (new_status, judgment[:200], review_id),
        )
        _write_audit(conn, review_id, "human_confirm", req)
        conn.commit(); conn.close()
        return {"review_id": review_id, "action": req.action, "status": new_status}

    # ── 3. 驳回：检查是否触发重检索 ──
    row = conn.execute(
        "SELECT retry_count, case_summary, charges, core_disputes FROM annotated_cases WHERE case_id=?",
        (review_id,),
    ).fetchone()
    if not row:
        conn.close()
        return {"review_id": review_id, "action": req.action, "status": "rejected", "error": "案件不存在"}

    retry_count, case_summary, charges_json, disputes_json = row
    note = (req.note or "").strip()

    # 驳回原因太短，不触发重检索
    if len(note) < 5:
        judgment = f"人工驳回（原因过短，未重检索）: {note}"
        conn.execute(
            "UPDATE annotated_cases SET review_status='rejected', judgment_key=? WHERE case_id=?",
            (judgment[:200], review_id),
        )
        _write_audit(conn, review_id, "human_reject_skip", req, detail_extra={"reason": "note_too_short"})
        conn.commit(); conn.close()
        return {"review_id": review_id, "action": req.action, "status": "rejected",
                "warning": "驳回原因不足5字，未触发重检索。请写明补证方向。"}

    # 已达最大重试次数
    if retry_count >= 3:
        judgment = f"人工驳回（已重试{retry_count}次，标记为需补证）: {note}"
        conn.execute(
            "UPDATE annotated_cases SET review_status='needs_supplement', judgment_key=? WHERE case_id=?",
            (judgment[:200], review_id),
        )
        _write_audit(conn, review_id, "human_reject_exhausted", req, detail_extra={"retry_count": retry_count})
        conn.commit(); conn.close()
        return {"review_id": review_id, "action": req.action, "status": "needs_supplement",
                "message": f"已重试{retry_count}次仍不通过，标记为需补证。请补充新材料后重新分析。"}

    # ── 4. 驳回重检索 ──
    # 聚合历史已见 chunk_id
    old_audit = conn.execute(
        "SELECT detail FROM audit_logs WHERE target_id=? AND action LIKE 'human_reject%' ORDER BY timestamp DESC",
        (review_id,),
    ).fetchall()
    seen_ids = set()
    for (d,) in old_audit:
        try:
            detail = json.loads(d)
            for cid in detail.get("chunk_ids", []):
                seen_ids.add(cid)
        except Exception:
            pass

    # 构建搜索查询：原案由 + 驳回原因作为补证方向
    try:
        charges = json.loads(charges_json) if charges_json else []
        disputes = json.loads(disputes_json) if disputes_json else []
    except Exception:
        charges, disputes = [], []

    search_parts = [case_summary or ""] + charges + disputes
    search_query = " ".join(p for p in search_parts if p)
    search_query = f"{search_query} 补充证据方向: {note}"

    # 检索新证据（排除已见过的） + 重算置信度
    retry_result = await _retry_retrieval_and_review(
        query=search_query,
        case_id=review_id,
        exclude_ids=list(seen_ids),
        retry_round=retry_count + 1,
    )

    new_confidence = retry_result["confidence"]
    new_chunks = retry_result["chunks"]

    # 写审计日志
    _write_audit(conn, review_id, f"human_reject_retry_{retry_count + 1}", req,
                 detail_extra={
                     "retry_round": retry_count + 1,
                     "search_query": search_query,
                     "new_confidence": new_confidence,
                     "new_chunks_count": len(new_chunks),
                     "chunk_ids": [c["chunk_id"] for c in new_chunks],
                 })

    # 判断：置信度是否改善
    if new_confidence >= 0.85:
        # 通过！自动转确认
        conn.execute(
            "UPDATE annotated_cases SET review_status='confirmed', judgment_key=?, retry_count=? WHERE case_id=?",
            (f"重检索通过（第{retry_count + 1}轮，置信度{new_confidence:.0%}）: {note}"[:200],
             retry_count + 1, review_id),
        )
        conn.commit(); conn.close()
        return {
            "review_id": review_id, "action": req.action,
            "status": "confirmed", "auto_confirmed": True,
            "retry_round": retry_count + 1, "new_confidence": new_confidence,
            "new_evidence": new_chunks,
        }
    elif new_confidence >= 0.70:
        # 有改善但仍不达标
        conn.execute(
            "UPDATE annotated_cases SET retry_count=?, judgment_key=? WHERE case_id=?",
            (retry_count + 1,
             f"第{retry_count + 1}轮重检索（置信度{new_confidence:.0%}）: {note}"[:200],
             review_id),
        )
        conn.commit(); conn.close()
        return {
            "review_id": review_id, "action": req.action,
            "status": "retrying", "retry_round": retry_count + 1,
            "retries_remaining": 3 - (retry_count + 1),
            "new_confidence": new_confidence,
            "new_evidence": new_chunks,
            "message": f"检索到{len(new_chunks)}条新证据，置信度{new_confidence:.0%}，仍需进一步补证。还可驳回{3 - (retry_count + 1)}次。",
        }
    else:
        # 未改善
        conn.execute(
            "UPDATE annotated_cases SET retry_count=?, judgment_key=? WHERE case_id=?",
            (retry_count + 1,
             f"第{retry_count + 1}轮重检索未改善（置信度{new_confidence:.0%}）: {note}"[:200],
             review_id),
        )
        conn.commit(); conn.close()
        return {
            "review_id": review_id, "action": req.action,
            "status": "retrying" if retry_count + 1 < 3 else "needs_supplement",
            "retry_round": retry_count + 1,
            "retries_remaining": max(0, 3 - (retry_count + 1)),
            "new_confidence": new_confidence,
            "new_evidence": new_chunks,
            "message": f"检索结果未显著改善（置信度{new_confidence:.0%}）。建议调整补证方向后重试。" if retry_count + 1 < 3
                       else f"已达最大重试次数（3次），标记为需补证。",
        }


# ══════════════════════════════════════════════════════════════════════
# 复核辅助函数
# ══════════════════════════════════════════════════════════════════════

def _ensure_schema(conn):
    """确保 audit_logs 表 + annotated_cases 扩展字段存在。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id       TEXT PRIMARY KEY,
            timestamp    TEXT NOT NULL,
            user_id      TEXT NOT NULL DEFAULT 'human_reviewer',
            action       TEXT NOT NULL,
            target_type  TEXT NOT NULL DEFAULT '',
            target_id    TEXT,
            detail       TEXT DEFAULT '{}',
            model_version TEXT DEFAULT '',
            ip_address   TEXT DEFAULT ''
        )
    """)
    # 添加 retry_count 列（如果不存在）
    try:
        conn.execute("ALTER TABLE annotated_cases ADD COLUMN retry_count INTEGER DEFAULT 0")
    except Exception:
        pass  # 列已存在


def _write_audit(conn, review_id: str, action: str, req, detail_extra=None):
    """写入一条审计日志。"""
    import json, uuid
    from datetime import datetime, timezone

    detail = {
        "review_id": review_id,
        "action": req.action,
        "note": req.note,
    }
    if detail_extra:
        detail.update(detail_extra)

    conn.execute(
        """INSERT INTO audit_logs (log_id, timestamp, user_id, action, target_type, target_id, detail, model_version, ip_address)
           VALUES (?, ?, 'human_reviewer', ?, 'annotated_case', ?, ?, '', '')""",
        (
            str(uuid.uuid4()),
            datetime.now(timezone.utc).isoformat(),
            action,
            review_id,
            json.dumps(detail, ensure_ascii=False),
        ),
    )


async def _retry_retrieval_and_review(
    query: str,
    case_id: str,
    exclude_ids: list[str],
    retry_round: int,
) -> dict:
    """执行一轮重检索 + 置信度重算。

    Returns:
        {"confidence": float, "chunks": list[dict], "dimensions": list[dict]}
    """
    from judicial_evidence_agent.core.evidence_chain import EvidenceChainAnalyzer
    from judicial_evidence_agent.core.agents.base import AgentContext
    from judicial_evidence_agent.core.agents.confidence_reviewer import ConfidenceReviewerAgent

    # ── 检索（排除已见 chunk）──
    analyzer = EvidenceChainAnalyzer(use_stub=False)
    chunks = analyzer.retrieve(query, top_k=10, case_id=case_id, exclude_ids=exclude_ids)

    # ── 构建最小上下文，重算置信度 ──
    ctx = AgentContext(case_id=case_id, query=query)
    ctx.retrieved_chunks = chunks

    # 从已有证据链中提取要素（用于维度计算）
    chunk_texts = [c["content"] for c in chunks if c.get("content")]
    ctx.extracted_elements = [
        {"category": "证据片段", "value": t[:80], "confidence": 0.7}
        for t in chunk_texts[:10]
    ]
    ctx.evidence_chains = [{
        "chain_id": f"retry-{retry_round}",
        "fact_to_prove": query[:60],
        "confidence": 0.5,
        "status": "review",
        "supporting_evidence": [{"chunk_id": c["chunk_id"]} for c in chunks[:5]],
        "missing_evidence": [],
    }]
    ctx.graph_nodes = [{"id": c["chunk_id"], "type": "evidence"} for c in chunks]
    ctx.graph_edges = []

    reviewer = ConfidenceReviewerAgent()
    ctx = await reviewer.run(ctx)

    return {
        "confidence": ctx.final_confidence,
        "chunks": [
            {
                "chunk_id": c["chunk_id"],
                "source_type": c.get("source_type", ""),
                "content_preview": c.get("content", "")[:150],
                "distance": c.get("distance", 0),
                "evidence_type": c.get("evidence_type", ""),
            }
            for c in chunks[:8]
        ],
        "dimensions": ctx.confidence_dimensions,
        "threshold": ctx.threshold_result,
    }


# ============================================================================
# 前端静态文件 (SPA)
# ============================================================================

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent.parent / "ui" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
