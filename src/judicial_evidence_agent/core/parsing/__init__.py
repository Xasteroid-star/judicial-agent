"""Document parsing — 多模态材料文本提取。

支持: PDF、纯文本。后期扩展: DOCX、图片 OCR、音频 ASR。
"""

from judicial_evidence_agent.core.parsing.pdf_parser import PdfParser

__all__ = ["PdfParser"]
