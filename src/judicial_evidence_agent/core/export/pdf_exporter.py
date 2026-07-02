"""PDF 报告导出 — 基于 fpdf2 + 中文系统字体。

支持:
- 中文正文（微软雅黑）+ 标题（黑体）
- Markdown 章节解析（## 标题 / **加粗** / - 列表 / 表格 / ``` 代码块）
- 页眉页脚（案件名称 + 页码）
- 自动分页
"""

from __future__ import annotations

import io
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 字体路径探测 ──────────────────────────────────────────────────────


def _find_system_font(name_patterns: list[str]) -> Optional[str]:
    """在 Windows 字体目录中查找字体文件。"""
    import glob
    font_dirs = [
        "C:/Windows/Fonts",
        "/usr/share/fonts",
        "/System/Library/Fonts",
    ]
    for font_dir in font_dirs:
        for pattern in name_patterns:
            matches = glob.glob(f"{font_dir}/{pattern}")
            if matches:
                return matches[0]
    return None


# 字体优先级：微软雅黑 > 黑体 > Noto Sans SC > 宋体
_BODY_FONT_CANDIDATES = ["msyh.ttc", "msyh.ttf", "NotoSansSC-VF.ttf", "simsun.ttc"]
_HEADING_FONT_CANDIDATES = ["simhei.ttf", "msyhbd.ttf", "NotoSansSC-VF.ttf", "simsun.ttc"]
_MONO_FONT_CANDIDATES = ["simsun.ttc", "simhei.ttf", "msyh.ttc"]


# ══════════════════════════════════════════════════════════════════════


class PdfExporter:
    """Markdown 报告 → PDF。

    用法:
        exporter = PdfExporter()
        pdf_bytes = exporter.export(
            report={"case_name": "张某交通肇事案", "status": "confirmed"},
            markdown=report_markdown_text,
        )
        with open("报告.pdf", "wb") as f:
            f.write(pdf_bytes)
    """

    def __init__(self):
        self._body_font: Optional[str] = None
        self._heading_font: Optional[str] = None
        self._mono_font: Optional[str] = None

    # ── 公共 API ──────────────────────────────────────────────────

    def export(
        self,
        report: dict,
        markdown: str,
        title: str = "",
    ) -> bytes:
        """导出 PDF，返回字节流。

        Args:
            report: 报告元数据（case_name, status 等）。
            markdown: 报告的 Markdown 正文。
            title: 可选标题，默认取 report["title"] 或 "证据链审查报告"。

        Returns:
            PDF 文件的字节内容。
        """
        from fpdf import FPDF

        # 清洗 emoji / 特殊字符（CJK 字体通常不含 emoji）
        markdown = _sanitize_for_cjk_font(markdown)

        # 探测字体（首次调用时）
        if self._body_font is None:
            self._body_font = _find_system_font(_BODY_FONT_CANDIDATES)
            self._heading_font = _find_system_font(_HEADING_FONT_CANDIDATES)
            self._mono_font = _find_system_font(_MONO_FONT_CANDIDATES)

            if not self._body_font:
                raise RuntimeError(
                    "未找到中文字体。请确保系统安装了微软雅黑(msyh.ttc)或宋体(simsun.ttc)。"
                )

            logger.info(
                "PDF 字体: body=%s heading=%s mono=%s",
                Path(self._body_font).stem,
                Path(self._heading_font or self._body_font).stem,
                Path(self._mono_font or self._body_font).stem,
            )

        # 回退：标题字体 → 正文字体
        heading_font = self._heading_font or self._body_font
        mono_font = self._mono_font or self._body_font

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)

        # ── 注册字体 ──
        pdf.add_font("Body", "", self._body_font, uni=True)
        pdf.add_font("Heading", "", heading_font, uni=True)
        pdf.add_font("Mono", "", mono_font, uni=True)

        # ── 元信息 ──
        case_name = report.get("case_name", "") or "案件"
        pdf_title = title or report.get("title", "") or f"{case_name} — 证据链审查报告"
        pdf.set_title(pdf_title)

        # ── 逐节渲染 ──
        self._render(pdf, report, markdown, case_name)

        # 输出为字节
        result = pdf.output()
        # fpdf2 可能返回 bytearray，Starlette Response 需要 bytes
        return bytes(result)

    # ── 渲染引擎 ──────────────────────────────────────────────────

    def _render(
        self,
        pdf,
        report: dict,
        markdown: str,
        case_name: str,
    ) -> None:
        """主渲染循环：逐行解析 markdown，按语义排版。"""
        # 字体尺寸
        BODY_SIZE = 10.5
        HEADING1_SIZE = 16
        HEADING2_SIZE = 13
        SMALL_SIZE = 8
        LINE_H = 6.5

        # 页面边距
        LEFT_MARGIN = 20
        pdf.set_left_margin(LEFT_MARGIN)
        pdf.set_right_margin(20)

        # ── 封面 ──
        pdf.add_page()
        pdf.ln(30)
        pdf.set_font("Heading", "", HEADING1_SIZE)
        pdf.multi_cell(0, 12, case_name, align="C")
        pdf.ln(6)
        pdf.set_font("Heading", "", HEADING2_SIZE)
        pdf.multi_cell(0, 10, "证据链审查报告", align="C")
        pdf.ln(8)

        status = report.get("status", "")
        status_label = {
            "confirmed": "[通过] 已确认", "rejected": "[驳回] 已驳回",
            "needs_supplement": "[!] 需补充", "pass": "[通过] 通过",
            "review": "[!] 需复核", "reject": "[驳回] 驳回",
        }.get(status, status or "—")

        pdf.set_font("Body", "", BODY_SIZE)
        pdf.multi_cell(0, LINE_H, f"审查结果：{status_label}", align="C")
        pdf.ln(4)
        pdf.set_font("Body", "", SMALL_SIZE)
        pdf.multi_cell(
            0, LINE_H,
            f"生成时间：{report.get('created_at', '') or '—'}",
            align="C",
        )

        # ── 正文 ──
        pdf.add_page()

        # 页眉
        pdf.set_font("Body", "", SMALL_SIZE)
        pdf.cell(0, LINE_H, case_name, align="L")
        pdf.ln(LINE_H * 1.5)

        # 逐行解析
        lines = markdown.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # ── ## 二级标题 ──
            if line.startswith("## "):
                title_text = line[3:].strip()
                pdf.ln(4)
                pdf.set_font("Heading", "", HEADING2_SIZE)
                pdf.multi_cell(0, LINE_H * 1.5, title_text)
                pdf.ln(2)
                pdf.set_font("Body", "", BODY_SIZE)
                i += 1
                continue

            # ── ### 三级标题 ──
            if line.startswith("### "):
                title_text = line[4:].strip()
                pdf.ln(3)
                pdf.set_font("Heading", "", 11)
                pdf.multi_cell(0, LINE_H * 1.3, title_text)
                pdf.ln(1)
                pdf.set_font("Body", "", BODY_SIZE)
                i += 1
                continue

            # ── ``` 代码块 ──
            if line.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # 跳过结尾 ```

                if code_lines:
                    pdf.set_font("Mono", "", SMALL_SIZE)
                    for cl in code_lines:
                        pdf.cell(0, LINE_H * 0.85, cl[:100], new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Body", "", BODY_SIZE)
                    pdf.ln(2)
                continue

            # ── 表格行 | ... | ──
            if line.strip().startswith("|") and line.strip().endswith("|"):
                # 跳过表头分隔线
                if re.match(r'^\|[\s\-:]+\|$', line.strip()):
                    i += 1
                    continue
                # 简单渲染为对齐文本（避免 fpdf2 复杂表格）
                cells = [c.strip() for c in line.split("|")[1:-1]]
                pdf.set_font("Mono", "", SMALL_SIZE)
                cell_text = "  │  ".join(cells)
                pdf.cell(0, LINE_H * 0.85, cell_text, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Body", "", BODY_SIZE)
                i += 1
                continue

            # ── 列表项 - / 1. / * ──
            if re.match(r'^(\s*[-*]\s|\s*\d+[\.\)]\s)', line):
                bullet = re.sub(r'^(\s*)([-*\d+\.\)]+)\s.*', r'\1\2', line)
                content = re.sub(r'^\s*[-*\d+\.\)]+\s', '', line)

                # 处理加粗 **...**
                pdf.set_font("Body", "", BODY_SIZE)
                pdf.set_x(LEFT_MARGIN + 5)
                self._write_rich_text(pdf, content, BODY_SIZE, LINE_H)
                i += 1
                continue

            # ── **加粗** 行 ──
            if line.startswith("**"):
                self._write_rich_text(pdf, line, BODY_SIZE, LINE_H, heading_size=11)
                i += 1
                continue

            # ── 普通段落 ──
            if line.strip():
                self._write_rich_text(pdf, line, BODY_SIZE, LINE_H)
            else:
                pdf.ln(LINE_H * 0.5)

            i += 1

    def _write_rich_text(
        self,
        pdf,
        text: str,
        body_size: float,
        line_h: float,
        heading_size: float = 0,
    ) -> None:
        """写入带加粗标记的文本行。

        处理 **bold** 标记，用 Heading 字体输出加粗部分，
        Body 字体输出普通部分。
        """
        from fpdf import FPDF

        parts = re.split(r'(\*\*[^*]+\*\*)', text)

        # 检查当前行是否有足够的空间容纳至少 2 行文字
        # 如果不足，自动换页
        if pdf.get_y() > pdf.h - 30:
            pdf.add_page()

        # 逐段写入
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                # 加粗文本
                bold_text = part[2:-2]
                pdf.set_font("Heading", "", heading_size or body_size + 0.5)
                pdf.write(line_h, bold_text)
            else:
                # 普通文本
                pdf.set_font("Body", "", body_size)
                pdf.write(line_h, part)

        pdf.ln(line_h)


# ── 便捷函数 ──────────────────────────────────────────────────────────


def _sanitize_for_cjk_font(text: str) -> str:
    """清洗 CJK 字体不支持的字符（emoji、变体选择器等）。

    - ⚠️ → [!]
    - ✅ → [V]
    - ❌ → [X]
    - 📋 → [*]
    - 📄 → [#]
    - 📍 → [>]
    - 🔴/🟡/🟢/⚪ → [高]/[中]/[低]/[-]
    - 零宽字符、变体选择器 → 删除
    """
    emoji_map = {
        "⚠️": "[!]", "⚠": "[!]",
        "✅": "[V]",
        "❌": "[X]",
        "📋": "[*]",
        "📄": "[#]",
        "📍": "[>]",
        "📎": "[@]",
        "🔴": "[高]", "🟡": "[中]", "🟢": "[低]", "⚪": "[-]",
        "💡": "[i]",
        "️": "",  # 变体选择器
        "​": "",  # 零宽空格
        "‍": "",  # 零宽连接符
    }
    for emoji, replacement in emoji_map.items():
        text = text.replace(emoji, replacement)
    return text


def export_report_pdf(
    report: dict,
    markdown: str,
    title: str = "",
) -> bytes:
    """便捷函数：导出报告为 PDF 字节流。

    Args:
        report: 报告元数据（包含 case_name, status 等）。
        markdown: Markdown 格式的报告正文。
        title: 可选标题。

    Returns:
        PDF 文件的字节内容，可直接写入 Response 或文件。
    """
    exporter = PdfExporter()
    result = exporter.export(report, markdown, title=title)
    # 确保返回 bytes（fpdf2 可能返回 bytearray）
    return bytes(result)
