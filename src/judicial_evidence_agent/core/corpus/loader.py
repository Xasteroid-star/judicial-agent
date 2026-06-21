"""Corpus loader — 从文件夹发现并加载全部法规。

参考 Patchwork-Assurance Seam 1 模式：
- 每条法规 = 一个 .md + 一个 .meta.yaml
- Loader 自动扫描 corpus/ 目录
- 元数据在加载时校验，格式错误立即报错
- 返回的 LawDocument 列表由检索和报告模块消费
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from judicial_evidence_agent.core.corpus.metadata import LawMetadata

# corpus/ 相对于项目根目录的位置
CORPUS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "corpus"


@dataclass
class LawDocument:
    """加载后的法规文档 — 文本 + 解析后的元数据。"""

    law_id: str
    text: str
    metadata: LawMetadata
    # 按章节/article 分割的 chunk 列表（后续由 chunk.py 填充）
    chunks: list[dict] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"LawDocument({self.law_id}: {self.metadata.law_name[:40]}...)"


def discover_corpus(corpus_dir: Path | None = None) -> list[Path]:
    """扫描 corpus/ 目录，返回所有 `.meta.yaml` 的路径列表。

    每条法规只需找到 meta 文件，同名 .md 在加载时配对。
    """
    root = corpus_dir or CORPUS_DIR
    return sorted(root.glob("*.meta.yaml"))


def load_law(meta_path: Path) -> LawDocument:
    """加载单条法规：读取 .md 文本 + 解析 .meta.yaml 并校验。

    校验失败会直接抛出 ValidationError，不静默跳过。
    """
    # 加载元数据
    with open(meta_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    metadata = LawMetadata(**raw)

    # 加载法条原文：criminal_procedure_evidence.meta.yaml -> criminal_procedure_evidence.md
    md_path = meta_path.parent / meta_path.name.replace(".meta.yaml", ".md")
    if not md_path.exists():
        raise FileNotFoundError(f"缺少法条原文文件: {md_path}")

    with open(md_path, encoding="utf-8") as fh:
        text = fh.read()

    return LawDocument(law_id=metadata.law_id, text=text, metadata=metadata)


def load_corpus(corpus_dir: Path | None = None) -> list[LawDocument]:
    """加载整个语料库：扫描并加载所有法规。

    这是系统中所有需要「法条原文」的模块的统一入口。
    API、RAG、报告生成都通过此函数获取法规。
    """
    docs = []
    for meta_path in discover_corpus(corpus_dir):
        docs.append(load_law(meta_path))
    return docs


def get_corpus_stats(docs: list[LawDocument] | None = None) -> dict:
    """返回语料库统计信息。"""
    if docs is None:
        docs = load_corpus()
    return {
        "total_laws": len(docs),
        "total_articles": sum(
            doc.metadata.articles_count or 0 for doc in docs
        ),
        "jurisdictions": list({doc.metadata.jurisdiction for doc in docs}),
        "domains": list({d for doc in docs for d in doc.metadata.scope_domains}),
    }
