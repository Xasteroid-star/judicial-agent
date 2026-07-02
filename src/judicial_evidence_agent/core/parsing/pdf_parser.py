"""PDF 文本提取 — 基于 pymupdf (fitz)。

提取每一页的文本 + 页码，生成带 source_pointer 的结构化输出。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PageText:
    """单页提取结果。"""

    page_number: int  # 1-indexed
    text: str
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.text)


@dataclass
class PdfDocument:
    """PDF 文档解析结果。"""

    file_path: str
    file_hash: str
    total_pages: int
    total_chars: int
    pages: list[PageText] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """拼接全部页面文本（页面间用换行分隔）。"""
        return "\n\n".join(p.text for p in self.pages)


class PdfParser:
    """PDF 文本提取器。

    用法:
        parser = PdfParser()
        doc = parser.parse("/path/to/file.pdf")
        for page in doc.pages:
            print(f"第 {page.page_number} 页: {page.text[:100]}...")
    """

    def parse(self, file_path: str | Path) -> PdfDocument:
        """解析 PDF 文件，按页提取文本。

        Args:
            file_path: PDF 文件路径。

        Returns:
            PdfDocument: 包含逐页文本的结构化文档。

        Raises:
            FileNotFoundError: 文件不存在。
            ValueError: 文件不是有效的 PDF。
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_hash = self._compute_hash(file_path)

        try:
            import fitz  # pymupdf
        except ImportError:
            raise ImportError(
                "pymupdf 未安装。请运行: pip install pymupdf"
            )

        pages: list[PageText] = []
        total_chars = 0

        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            raise ValueError(f"无法打开 PDF 文件: {file_path} — {e}")

        try:
            for page_index in range(len(doc)):
                page = doc[page_index]
                text = page.get_text("text")  # 纯文本模式
                text = self._clean_text(text)

                pt = PageText(
                    page_number=page_index + 1,  # 1-indexed
                    text=text,
                )
                pages.append(pt)
                total_chars += pt.char_count
        finally:
            doc.close()

        return PdfDocument(
            file_path=str(file_path),
            file_hash=file_hash,
            total_pages=len(pages),
            total_chars=total_chars,
            pages=pages,
        )

    # ── 私有方法 ──────────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        """计算文件 SHA-256（用于去重和溯源）。"""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def _clean_text(text: str) -> str:
        """清洗提取的文本。

        - 合并多余空白行
        - 删除零宽字符
        - 规范化换行
        """
        # 删除零宽字符
        text = text.replace("​", "").replace("‌", "").replace("‍", "")
        text = text.replace("﻿", "")  # BOM
        text = text.replace(" ", " ")  # 不间断空格 → 普通空格

        # 合并 3+ 连续换行为 2 个
        import re
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 去除首尾空白
        text = text.strip()

        return text


def extract_pdf_pages(file_path: str | Path) -> list[PageText]:
    """便捷函数：提取 PDF 所有页面的文本。

    Returns:
        list[PageText]: 按页码排序的页面文本列表。
    """
    parser = PdfParser()
    doc = parser.parse(file_path)
    return doc.pages
