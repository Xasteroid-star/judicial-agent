"""Ingestion pipeline — 材料摄入完整管线。

流程: 文件上传 → 类型检测 → 文本提取 → 分块 → 写入 SQLite → 重建向量索引。

用法:
    pipeline = IngestionPipeline()
    result = await pipeline.ingest_pdf(
        file_bytes=b"...",
        filename="起诉书.pdf",
        case_id="case-uuid-here",
    )
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 项目根目录（core/ingestion/pipeline.py → 上溯 5 层到项目根）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


class IngestionPipeline:
    """材料摄入管线。

    将上传的文件解析、分块、入库，并可选重建向量索引。

    用法:
        pipeline = IngestionPipeline()
        result = await pipeline.ingest(
            file_bytes=...,
            filename="证据材料.pdf",
            case_id="some-case-id",
            rebuild_index=True,
        )
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        storage_dir: str | Path | None = None,
    ):
        self.db_path = str(db_path or (_PROJECT_ROOT / "data" / "judicial_evidence.db"))
        self.storage_dir = Path(storage_dir or (_PROJECT_ROOT / "data" / "materials"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # ── 公共 API ──────────────────────────────────────────────────────

    async def ingest(
        self,
        file_bytes: bytes,
        filename: str,
        case_id: str,
        rebuild_index: bool = False,
    ) -> dict:
        """摄入单个文件：解析 → 分块 → 入库。

        Args:
            file_bytes: 文件的原始字节。
            filename: 原始文件名（用于类型检测）。
            case_id: 关联的案件 ID。
            rebuild_index: 是否在摄入后重建向量索引（默认 False，批量摄入后手动重建）。

        Returns:
            {
                "material_id": str,
                "filename": str,
                "file_hash": str,
                "total_pages": int,
                "total_chunks": int,
                "chunk_ids": list[str],
                "file_path": str,
                "index_rebuilt": bool,
            }
        """
        # 1. 检测文件类型
        file_type = self._detect_type(filename, file_bytes)

        # 2. 保存文件到 storage
        file_path, file_hash = self._save_file(file_bytes, filename)

        # 3. 注册 material 记录
        material_id = self._register_material(
            case_id=case_id,
            name=filename,
            file_type=file_type,
            file_hash=file_hash,
            file_path=str(file_path),
        )

        # 4. 提取文本
        if file_type == "pdf":
            pages = self._extract_pdf_text(file_path)
        else:
            # 纯文本：整个文件作为一个"页面"
            text = self._try_decode(file_bytes)
            pages = [{"page_number": 1, "text": text}]

        # 5. 分块
        chunks = self._chunk_pages(pages, case_id, material_id)

        # 6. 写入 evidence_chunks 表
        self._write_chunks(chunks)

        # 7. 可选重建索引
        index_rebuilt = False
        if rebuild_index:
            index_rebuilt = self._rebuild_index()

        logger.info(
            "摄入完成: %s → material=%s, %d chunks (pages=%d)",
            filename, material_id, len(chunks), len(pages),
        )

        return {
            "material_id": material_id,
            "filename": filename,
            "file_hash": file_hash,
            "total_pages": len(pages),
            "total_chunks": len(chunks),
            "chunk_ids": [c["chunk_id"] for c in chunks],
            "file_path": str(file_path),
            "index_rebuilt": index_rebuilt,
        }

    # ── 私有方法 ──────────────────────────────────────────────────────

    @staticmethod
    def _detect_type(filename: str, file_bytes: bytes) -> str:
        """检测文件类型。"""
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            # 验证 PDF 魔数
            if file_bytes[:4] == b"%PDF":
                return "pdf"
            raise ValueError(f"文件扩展名为 .pdf 但内容不是有效的 PDF")

        if ext in (".txt", ".md", ".csv"):
            return "text"

        if ext in (".docx", ".doc"):
            return "docx"  # 后期实现

        if ext in (".xlsx", ".xls"):
            return "xlsx"  # 后期实现

        # 尝试作为文本解码
        try:
            file_bytes.decode("utf-8")
            return "text"
        except UnicodeDecodeError:
            pass

        raise ValueError(f"不支持的文件类型: {ext}")

    def _save_file(self, file_bytes: bytes, filename: str) -> tuple[Path, str]:
        """保存文件到本地存储，返回 (路径, hash)。"""
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # 按 hash 存，避免重复文件
        ext = Path(filename).suffix
        safe_name = f"{file_hash}{ext}"
        dest = self.storage_dir / safe_name

        if not dest.exists():
            dest.write_bytes(file_bytes)

        return dest, file_hash

    def _register_material(
        self,
        case_id: str,
        name: str,
        file_type: str,
        file_hash: str,
        file_path: str,
    ) -> str:
        """在 materials 表中注册材料记录。"""
        material_id = f"MAT-{file_hash[:12]}"

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO materials
                   (material_id, case_id, name, type, file_hash, file_path, processing_status)
                   VALUES (?,?,?,?,?,?,?)""",
                (material_id, case_id, name, file_type, file_hash, file_path, "completed"),
            )
            conn.commit()
        finally:
            conn.close()

        return material_id

    @staticmethod
    def _extract_pdf_text(file_path: Path) -> list[dict]:
        """提取 PDF 文本，返回逐页 dict。"""
        from judicial_evidence_agent.core.parsing.pdf_parser import PdfParser

        parser = PdfParser()
        doc = parser.parse(file_path)

        return [
            {
                "page_number": p.page_number,
                "text": p.text,
                "char_count": p.char_count,
            }
            for p in doc.pages
        ]

    @staticmethod
    def _try_decode(file_bytes: bytes) -> str:
        """尝试解码字节为文本（UTF-8 / GBK）。"""
        for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
            try:
                return file_bytes.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        return file_bytes.decode("utf-8", errors="replace")

    def _chunk_pages(
        self,
        pages: list[dict],
        case_id: str,
        material_id: str,
        max_chars: int = 500,
        overlap: int = 50,
    ) -> list[dict]:
        """将逐页文本切分为 EvidenceChunk。

        策略：
        - 每个页面独立切分（不跨页）
        - 按句号/分号/换行自然断句
        - 超过 max_chars 时才切分
        - 每个 chunk 携带 source_pointer.page
        """
        import re

        chunks = []
        chunk_index = 0

        for page in pages:
            page_num = page["page_number"]
            text = page["text"]

            if not text.strip():
                continue

            # 按标点断句
            sentences = re.split(r"[。；\n]", text)
            sentences = [s.strip() for s in sentences if s.strip()]

            if not sentences:
                continue

            current = ""
            sent_start = 0

            for i, sent in enumerate(sentences):
                if len(current) + len(sent) > max_chars and current:
                    # 保存当前 chunk
                    chunks.append(self._make_chunk(
                        case_id=case_id,
                        material_id=material_id,
                        index=chunk_index,
                        text=current.strip(),
                        page=page_num,
                        sentence_range=f"{sent_start}-{i - 1}",
                    ))
                    chunk_index += 1

                    # 重叠：保留最后一句
                    if overlap > 0 and i > 0:
                        current = sentences[i - 1] + "。" + sent
                        sent_start = i - 1
                    else:
                        current = sent
                        sent_start = i
                else:
                    if current:
                        current += "。"
                    current += sent

            # 最后一段
            if current.strip():
                chunks.append(self._make_chunk(
                    case_id=case_id,
                    material_id=material_id,
                    index=chunk_index,
                    text=current.strip(),
                    page=page_num,
                    sentence_range=f"{sent_start}-{len(sentences) - 1}",
                ))
                chunk_index += 1

        return chunks

    @staticmethod
    def _make_chunk(
        case_id: str,
        material_id: str,
        index: int,
        text: str,
        page: int,
        sentence_range: str,
    ) -> dict:
        """构造单个 EvidenceChunk dict。"""
        chunk_id = f"{case_id}:{material_id}:chunk_{index:04d}"
        return {
            "chunk_id": chunk_id,
            "case_id": case_id,
            "material_id": material_id,
            "modality": "text",
            "content_text": text,
            "extracted_elements": json.dumps({}, ensure_ascii=False),
            "source_pointer": json.dumps({
                "material_id": material_id,
                "page": page,
                "sentence_range": sentence_range,
            }, ensure_ascii=False),
            "confidence": 1.0,
            "model_version": "",
            "created_at": datetime.utcnow().isoformat(),
        }

    def _write_chunks(self, chunks: list[dict]) -> None:
        """批量写入 evidence_chunks 表。"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executemany(
                """INSERT OR REPLACE INTO evidence_chunks
                   (chunk_id, case_id, material_id, modality, content_text,
                    extracted_elements, source_pointer, confidence, model_version, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        c["chunk_id"],
                        c["case_id"],
                        c["material_id"],
                        c["modality"],
                        c["content_text"],
                        c["extracted_elements"],
                        c["source_pointer"],
                        c["confidence"],
                        c["model_version"],
                        c["created_at"],
                    )
                    for c in chunks
                ],
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("写入 %d 条 chunk 到 evidence_chunks", len(chunks))

    @staticmethod
    def _rebuild_index() -> bool:
        """重建 BGE 向量索引。

        调用 build_vector_index.py 中的 build_index() 函数。
        如果索引构建失败，记录警告但不阻断摄入流程。
        """
        try:
            import subprocess
            import sys

            script = _PROJECT_ROOT / "scripts" / "build_vector_index.py"
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
            )
            if result.returncode == 0:
                logger.info("向量索引重建成功")
                return True
            else:
                logger.warning("向量索引重建失败: %s", result.stderr[:500])
                return False
        except Exception as e:
            logger.warning("向量索引重建异常: %s", e)
            return False


# ── 便捷函数 ──────────────────────────────────────────────────────────

async def ingest_pdf_file(
    file_bytes: bytes,
    filename: str,
    case_id: str,
    rebuild_index: bool = True,
) -> dict:
    """便捷函数：摄入一个 PDF 文件。

    Args:
        file_bytes: PDF 文件字节。
        filename: 文件名。
        case_id: 关联案件 ID。
        rebuild_index: 是否自动重建索引（默认 True）。

    Returns:
        摄入结果 dict。
    """
    pipeline = IngestionPipeline()
    return await pipeline.ingest(
        file_bytes=file_bytes,
        filename=filename,
        case_id=case_id,
        rebuild_index=rebuild_index,
    )
