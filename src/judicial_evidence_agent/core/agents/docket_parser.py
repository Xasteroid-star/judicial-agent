"""卷宗解析 Agent — architecture.md §7

判断材料类型 → 加载已解析的 EvidenceChunk → 或触发 PDF/文本解析。
"""

import sqlite3
import json
import logging

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext

logger = logging.getLogger(__name__)


class DocketParserAgent(BaseAgent):
    """卷宗解析 Agent。

    职责：
    1. 从数据库加载案件关联的 materials 记录
    2. 对于已解析的材料，加载其 evidence_chunks
    3. 对于未解析的材料（processing_status != 'completed'），尝试触发解析
    4. 输出 material_ids 列表供下游 Agent 使用
    """

    name = "docket_parser"

    async def run(self, ctx: AgentContext) -> AgentContext:
        db_path = "data/judicial_evidence.db"
        conn = sqlite3.connect(db_path)

        try:
            # 1. 查询案件关联的所有 materials
            if ctx.case_id:
                rows = conn.execute(
                    """SELECT material_id, name, type, file_path, processing_status
                       FROM materials WHERE case_id=? ORDER BY created_at DESC""",
                    (ctx.case_id,),
                ).fetchall()
            else:
                rows = []

            if not rows:
                logger.info("案件 %s 无关联材料，跳过解析", ctx.case_id or "(未知)")
                ctx.material_ids = []
                ctx.processing_errors = []
                return ctx

            material_ids = []
            errors = []

            for r in rows:
                material_id, name, mtype, file_path, status = r
                material_ids.append(material_id)

                # 2. 对于尚未解析的材料（PENDING），尝试按类型触发解析
                if status != "completed" and file_path:
                    try:
                        logger.info("触发解析: %s (%s, %s)", name, mtype, material_id)
                        self._parse_material(material_id, mtype, file_path, db_path)
                    except Exception as e:
                        logger.warning("解析失败 %s: %s", name, e)
                        errors.append({"material_id": material_id, "name": name, "error": str(e)})

            # 3. 收集所有已解析的 chunk
            ctx.material_ids = material_ids
            ctx.processing_errors = errors

        finally:
            conn.close()

        return ctx

    # ── 私有方法 ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_material(
        material_id: str,
        mtype: str,
        file_path: str,
        db_path: str,
    ) -> None:
        """按材料类型路由到具体解析器。

        当前支持: PDF (pymupdf), 纯文本。
        后期扩展: DOCX, 图片 OCR, 音频 ASR。
        """
        from pathlib import Path

        fp = Path(file_path)
        if not fp.exists():
            logger.warning("材料文件不存在: %s", file_path)
            return

        if mtype == "pdf" or fp.suffix.lower() == ".pdf":
            pages = _extract_pdf(file_path)
        elif mtype in ("text", "document") or fp.suffix.lower() in (".txt", ".md", ".csv"):
            pages = _extract_text(file_path)
        else:
            logger.info("暂不支持的类型: %s，跳过解析", mtype)
            return

        # 切分 + 写入
        chunks = _chunk_pages(pages, material_id, "CASE-PLACEHOLDER")
        _write_chunks(chunks, db_path)
        _mark_completed(material_id, db_path)
        logger.info("解析完成: %s → %d chunks", material_id, len(chunks))


# ── 辅助函数 ──────────────────────────────────────────────────────────


def _extract_pdf(file_path: str) -> list[dict]:
    """提取 PDF 文本为逐页 dict。"""
    from judicial_evidence_agent.core.parsing.pdf_parser import PdfParser

    parser = PdfParser()
    doc = parser.parse(file_path)
    return [
        {"page_number": p.page_number, "text": p.text}
        for p in doc.pages
    ]


def _extract_text(file_path: str) -> list[dict]:
    """读取纯文本文件。"""
    from pathlib import Path
    text = Path(file_path).read_text(encoding="utf-8")
    return [{"page_number": 1, "text": text}]


def _chunk_pages(
    pages: list[dict],
    material_id: str,
    case_id: str,
    max_chars: int = 500,
) -> list[dict]:
    """将逐页文本切分为 EvidenceChunk dict。"""
    import re
    from datetime import datetime

    chunks = []
    chunk_index = 0

    for page in pages:
        page_num = page["page_number"]
        text = page["text"]
        if not text.strip():
            continue

        sentences = re.split(r"[。；\n]", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            continue

        current = ""
        sent_start = 0

        for i, sent in enumerate(sentences):
            if len(current) + len(sent) > max_chars and current:
                chunks.append({
                    "chunk_id": f"{case_id}:{material_id}:chunk_{chunk_index:04d}",
                    "case_id": case_id,
                    "material_id": material_id,
                    "modality": "text",
                    "content_text": current.strip(),
                    "extracted_elements": json.dumps({}, ensure_ascii=False),
                    "source_pointer": json.dumps({
                        "material_id": material_id,
                        "page": page_num,
                        "sentence_range": f"{sent_start}-{i - 1}",
                    }, ensure_ascii=False),
                    "confidence": 1.0,
                    "model_version": "",
                    "created_at": datetime.utcnow().isoformat(),
                })
                chunk_index += 1
                current = sent
                sent_start = i
            else:
                current += "。" + sent if current else sent

        if current.strip():
            chunks.append({
                "chunk_id": f"{case_id}:{material_id}:chunk_{chunk_index:04d}",
                "case_id": case_id,
                "material_id": material_id,
                "modality": "text",
                "content_text": current.strip(),
                "extracted_elements": json.dumps({}, ensure_ascii=False),
                "source_pointer": json.dumps({
                    "material_id": material_id,
                    "page": page_num,
                    "sentence_range": f"{sent_start}-{len(sentences) - 1}",
                }, ensure_ascii=False),
                "confidence": 1.0,
                "model_version": "",
                "created_at": datetime.utcnow().isoformat(),
            })
            chunk_index += 1

    return chunks


def _write_chunks(chunks: list[dict], db_path: str) -> None:
    """批量写入 evidence_chunks 表。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO evidence_chunks
               (chunk_id, case_id, material_id, modality, content_text,
                extracted_elements, source_pointer, confidence, model_version, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    c["chunk_id"], c["case_id"], c["material_id"],
                    c["modality"], c["content_text"],
                    c["extracted_elements"], c["source_pointer"],
                    c["confidence"], c["model_version"], c["created_at"],
                )
                for c in chunks
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _mark_completed(material_id: str, db_path: str) -> None:
    """标记材料为已解析。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE materials SET processing_status='completed' WHERE material_id=?",
            (material_id,),
        )
        conn.commit()
    finally:
        conn.close()
