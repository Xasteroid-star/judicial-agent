"""Report export — 报告导出（PDF / HTML）。

用法:
    exporter = PdfExporter()
    pdf_bytes = exporter.export(report_dict, report_markdown)

    html = HtmlExporter().export(report_dict, report_markdown)
"""

from judicial_evidence_agent.core.export.pdf_exporter import PdfExporter, export_report_pdf

__all__ = ["PdfExporter", "export_report_pdf"]
