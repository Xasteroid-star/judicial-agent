"""Evidence chunking — 将案件事实和证据列表切分为统一 EvidenceChunk。

参考 Patchwork-Assurance 的 chunk 策略（按结构切分、保留来源引用），
但适配司法场景：按证据项 + 事实段落切分，而非按法条章节。
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Optional


def make_chunk_id(law_id: str, chunk_index: int) -> str:
    """确定性 chunk ID，幂等写入。"""
    return f"{law_id}:chunk_{chunk_index:04d}"


def make_evidence_chunk_id(case_id: str, material_id: str, index: int) -> str:
    """证据片段 chunk ID。"""
    return f"{case_id}:{material_id}:chunk_{index:04d}"


def split_fact_as_chunks(
    fact: str,
    case_id: str,
    material_id: str,
    max_chars: int = 500,
    overlap: int = 50,
) -> list[dict]:
    """将案件事实描述切分为段落级 chunk。

    按句号/分号自然断句，size-bound 作为兜底。
    每个 chunk 携带来源元数据。
    """
    # 按标点断句
    sentences = re.split(r"[。；\n]", fact)
    # 过滤空句
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks = []
    current = ""
    index = 0
    sentence_idx_start = 0

    for i, sent in enumerate(sentences):
        if len(current) + len(sent) > max_chars and current:
            chunks.append({
                "chunk_id": make_evidence_chunk_id(case_id, material_id, index),
                "case_id": case_id,
                "material_id": material_id,
                "modality": "text",
                "content_text": current.strip(),
                "extracted_elements": {},
                "source_pointer": {
                    "material_id": material_id,
                    "paragraph": sentence_idx_start,
                    "content_range": f"sentence_{sentence_idx_start}_to_{i - 1}",
                },
                "confidence": 1.0,
                "model_version": "",
            })
            index += 1
            # 重叠：保留最后一句
            current = sentences[i - 1] + "。" + sent if overlap > 0 else sent
            sentence_idx_start = i - 1 if overlap > 0 else i
        else:
            if current:
                current += "。"
            current += sent

    # 最后一段
    if current.strip():
        chunks.append({
            "chunk_id": make_evidence_chunk_id(case_id, material_id, index),
            "case_id": case_id,
            "material_id": material_id,
            "modality": "text",
            "content_text": current.strip(),
            "extracted_elements": {},
            "source_pointer": {
                "material_id": material_id,
                "paragraph": sentence_idx_start,
                "content_range": f"sentence_{sentence_idx_start}_to_{len(sentences) - 1}",
            },
            "confidence": 1.0,
            "model_version": "",
        })

    return chunks


def evidence_items_to_chunks(
    evidence_list: list[dict],
    case_id: str,
    material_id: str,
) -> list[dict]:
    """将结构化证据列表转为 EvidenceChunk。

    每个证据项（书证/证人证言/鉴定意见等）成为一个独立的 chunk。
    """
    chunks = []
    for i, ev in enumerate(evidence_list):
        chunk = {
            "chunk_id": make_evidence_chunk_id(case_id, material_id, i),
            "case_id": case_id,
            "material_id": material_id,
            "modality": "text",  # 文本阶段；图片/视频后期升级
            "content_text": f"[{ev.get('type', '证据')}] {ev.get('name', '')}：{ev.get('description', '')}",
            "extracted_elements": {
                "evidence_type": ev.get("type", ""),
                "name": ev.get("name", ""),
                "collector": ev.get("collector", ""),
                "collect_date": ev.get("collect_date", ""),
            },
            "source_pointer": {
                "material_id": material_id,
                "page": None,
                "paragraph": i,
                "content_range": f"evidence_item_{i}",
            },
            "confidence": 1.0,  # 模拟数据默认高置信度
            "model_version": "",
        }
        chunks.append(chunk)

    return chunks


def case_to_chunks(case: dict) -> list[dict]:
    """将一条完整案件记录切分为 EvidenceChunk 列表。

    切分策略：
    1. 事实描述 → 按段落切分（max 500 chars, 50 char overlap）
    2. 证据列表 → 每个证据项一个 chunk
    """
    case_id = case["case_id"]
    material_id = hashlib.md5(
        (case_id + "material").encode()
    ).hexdigest()[:32]

    chunks = []

    # 事实描述切分
    if case.get("fact"):
        fact_chunks = split_fact_as_chunks(
            case["fact"], case_id, material_id
        )
        chunks.extend(fact_chunks)

    # 证据列表转 chunk
    if case.get("evidence_list"):
        ev_chunks = evidence_items_to_chunks(
            case["evidence_list"], case_id, material_id
        )
        chunks.extend(ev_chunks)

    return chunks


def split_law_as_chunks(
    text: str,
    law_id: str,
    metadata: dict | None = None,
    chunk_size: int = 800,
) -> list[dict]:
    """将法条原文按「条文编号」切分为 chunk。

    每条法规以 ### 第N条 为边界切分。
    每个 chunk 自带 citation（法律名 + 条文编号）+ 时效信息。
    如果单条过长（> chunk_size），再按句号二次切分。
    """
    meta = metadata or {}
    effective_date = meta.get("effective_date", "")
    law_name = meta.get("law_name", law_id)
    # 按条文边界切分：### 第N条（法律） 或 **第N条**（司法解释）
    # 注意：### 第五十条 中，### 后面是「第」，需要把「第」也纳入分隔符
    sections = re.split(
        r"\n(?=(?:### 第|\*\*第)[一二三四五六七八九十百零\d]+条)",
        text
    )

    chunks = []
    index = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # 提取条文编号（如 "第五十四条" 或 "第一条"）
        title_match = re.match(r"(?:### |\*\*)第([一二三四五六七八九十百零\d]+)条", section)
        article_title = f"第{title_match.group(1)}条" if title_match else f"片段{index}"

        # 如果单条太长，二次切分
        if len(section) > chunk_size:
            sentences = re.split(r"[。；]", section)
            current = ""
            sentence_start = 0
            sub_idx = 0
            for i, s in enumerate(sentences):
                s = s.strip()
                if not s:
                    continue
                if len(current) + len(s) > chunk_size and current:
                    chunks.append(_make_law_chunk(
                        law_id, index, current.strip(), article_title,
                        effective_date, law_name, sentence_start, i - 1,
                    ))
                    index += 1
                    sub_idx += 1
                    current = s
                    sentence_start = i
                else:
                    current += "；" + s if current else s
            if current.strip():
                chunks.append(_make_law_chunk(
                    law_id, index, current.strip(), article_title,
                    effective_date, law_name, sentence_start, len(sentences) - 1,
                ))
                index += 1
        else:
            chunks.append(_make_law_chunk(
                law_id, index, section.strip(), article_title,
                effective_date, law_name, 0, 0,
            ))
            index += 1

    return chunks


def _make_law_chunk(
    law_id: str,
    index: int,
    text: str,
    article_title: str,
    effective_date: str = "",
    law_name: str = "",
    sent_start: int = 0,
    sent_end: int = 0,
) -> dict:
    """构建法条 chunk，携带时效 + 来源元数据。"""
    return {
        "chunk_id": make_chunk_id(law_id, index),
        "law_id": law_id,
        "modality": "text",
        "content_text": text,
        "citation": article_title,
        "extracted_elements": {
            "source_type": "statute",
            "article": article_title,
            "law_name": law_name,
            "effective_date": effective_date,
        },
        "source_pointer": {
            "law_id": law_id,
            "article": article_title,
            "effective_date": effective_date,
            "sentence_range": f"{sent_start}-{sent_end}",
        },
        "confidence": 1.0,
        "model_version": "",
    }


def corpus_chunk_stats(chunks: list[dict]) -> dict:
    """统计 chunk 元信息。"""
    modalities = {}
    total_len = 0
    for c in chunks:
        m = c.get("modality", "unknown")
        modalities[m] = modalities.get(m, 0) + 1
        total_len += len(c.get("content_text", ""))

    return {
        "total_chunks": len(chunks),
        "total_chars": total_len,
        "avg_chars": total_len // max(len(chunks), 1),
        "modalities": modalities,
    }
