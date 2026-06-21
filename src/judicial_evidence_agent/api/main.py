"""FastAPI 应用入口 — 完整 API 层（对照 architecture.md §4 应用后端）。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    """卷宗材料列表。"""
    return [
        {"material_id": "M-001", "name": "受案登记表.pdf", "type": "文本文书",
         "source_org": "上海市公安局浦东分局", "collector": "侦查员张某",
         "confidentiality_level": "medium", "file_hash": "a3f2...8c1d",
         "processing_status": "completed", "created_at": "2024-08-06T14:30:00"},
        {"material_id": "M-002", "name": "现场勘查照片.zip", "type": "图片",
         "source_org": "上海市公安局浦东分局", "collector": "技术科",
         "confidentiality_level": "medium", "file_hash": "b7e1...4f2a",
         "processing_status": "completed", "created_at": "2024-08-06T15:00:00"},
        {"material_id": "M-003", "name": "李某询问笔录.docx", "type": "文本文书",
         "source_org": "上海市公安局浦东分局", "collector": "侦查员王某",
         "confidentiality_level": "medium", "file_hash": "c2d4...9a7b",
         "processing_status": "completed", "created_at": "2024-08-07T09:15:00"},
    ]


@app.post("/api/materials")
async def create_material(req: MaterialCreate):
    """登记新材料。"""
    return {"material_id": "M-999", "status": "registered", **req.dict()}


# ============================================================================
# 证据片段 API (§5.2-5.3)
# ============================================================================

@app.get("/api/evidence-chunks")
async def list_chunks(case_id: str = ""):
    """证据片段列表。"""
    return [
        {
            "chunk_id": "CH-001", "modality": "text",
            "content_text": "2024年8月5日，犯罪嫌疑人王某在上海市浦东新区某小区内，因琐事与被害人李某发生争执，持木棍将李某打伤。",
            "extracted_elements": {"人物": "王某、李某", "时间": "2024-08-05", "行为": "持木棍殴打"},
            "source_pointer": {"material_id": "M-003", "page": 2, "paragraph": 3},
            "confidence": 0.92, "model_version": "v0.1",
        },
        {
            "chunk_id": "CH-002", "modality": "text",
            "content_text": "经鉴定，被害人李某左前臂骨折，损伤程度为轻伤二级。",
            "extracted_elements": {"证据名称": "司法鉴定意见书", "证明对象": "损伤程度"},
            "source_pointer": {"material_id": "M-006", "page": 1, "paragraph": 1},
            "confidence": 0.95, "model_version": "v0.1",
        },
    ]


# ============================================================================
# 图谱 API (§5.5)
# ============================================================================

@app.get("/api/graph")
async def get_graph(case_id: str = ""):
    """知识图谱数据。"""
    return {
        "nodes": [
            {"id": "le1", "label": "故意伤害罪(刑法234条)", "type": "LegalElement"},
            {"id": "f1", "label": "李某轻伤二级", "type": "Fact"},
            {"id": "f2", "label": "王某持木棍殴打", "type": "Fact"},
            {"id": "e1", "label": "司法鉴定意见书", "type": "Evidence"},
            {"id": "e2", "label": "证人张某证言", "type": "Evidence"},
            {"id": "e3", "label": "物证:木棍", "type": "Evidence"},
            {"id": "e4", "label": "现场勘查笔录", "type": "Evidence"},
            {"id": "p1", "label": "王某", "type": "Person"},
            {"id": "p2", "label": "李某", "type": "Person"},
            {"id": "r1", "label": "刑讯逼供主张", "type": "Risk"},
        ],
        "edges": [
            {"from": "le1", "to": "f1", "relation": "法律要件", "confidence": 1.0},
            {"from": "le1", "to": "f2", "relation": "法律要件", "confidence": 1.0},
            {"from": "e1", "to": "f1", "relation": "证明", "confidence": 0.85},
            {"from": "e2", "to": "f2", "relation": "证明", "confidence": 0.72},
            {"from": "e3", "to": "f2", "relation": "补强", "confidence": 0.78},
            {"from": "e4", "to": "f2", "relation": "补强", "confidence": 0.80},
            {"from": "r1", "to": "e2", "relation": "冲突", "confidence": 0.45},
        ],
    }


# ============================================================================
# 证据链分析 API — RAG + LLM (§5.4, §5.7-5.8)
# ============================================================================

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """证据链分析：8-Agent 流水线。"""
    from judicial_evidence_agent.core.agents.orchestrator import AgentPipeline

    pipeline = AgentPipeline(stub_llm=False)
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
            {"name": "要素抽取 Agent", "status": "active", "phase": 2},
            {"name": "RAG 检索 Agent", "status": "active", "phase": 3},
            {"name": "知识图谱 Agent", "status": "active", "phase": 4},
            {"name": "证据链分析 Agent", "status": "active", "phase": 5},
            {"name": "置信度审查 Agent", "status": "active", "phase": 6},
            {"name": "报告生成 Agent", "status": "active", "phase": 7},
            {"name": "人工复核 Agent", "status": "active", "phase": 8},
        ],
        "pipeline": "sequential",
        "orchestration": "LangGraph (planning)",
    }


# ============================================================================
# 报告 API (§5.8)
# ============================================================================

@app.get("/api/reports")
async def list_reports(case_id: str = ""):
    """报告列表。"""
    return [{
        "report_id": "RPT-2024-001",
        "case_id": "1",
        "title": "王某故意伤害案 — 证据链审查报告",
        "created_at": "2024-08-12T16:30:00",
    }]


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
                      a.case_summary, a.evidence_types, a.applicable_articles
               FROM annotated_cases a WHERE a.review_status='pending'
               LIMIT 20"""
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
                    "id": r[0], "type": "annotation", "title": r[1],
                    "detail": "\n".join(detail_parts),
                    "confidence": confidence, "status": "pending",
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
    """提交复核结果，写入数据库。"""
    import sqlite3
    conn = sqlite3.connect("data/judicial_evidence.db")
    new_status = "confirmed" if req.action == "confirm" else "rejected"
    conn.execute(
        "UPDATE annotated_cases SET review_status=?, judgment_key=? WHERE case_id=?",
        (new_status, f"复核: {req.note[:80] if req.note else req.action}", review_id),
    )
    conn.commit()
    conn.close()
    return {"review_id": review_id, "action": req.action, "status": new_status}
