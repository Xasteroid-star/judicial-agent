"""Corpus metadata — Pydantic model for .meta.yaml validation.

参考 Patchwork-Assurance Seam 1：每条法规的元数据在加载时验证，
格式不完整或不正确的元数据在加载时立即报错。
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class LawMetadata(BaseModel):
    """法规元数据 — 对应 corpus/*.meta.yaml。

    所有字段在加载时验证，缺失必填字段直接报错。
    """

    law_id: str = Field(description="唯一标识，与文件名一致")
    jurisdiction: str = Field(description="法域（china / hong_kong 等）")
    law_name: str = Field(description="法规全称（中文）")
    law_type: str = Field(description="类型：statute / judicial_interpretation / regulation / guideline")
    citation: str = Field(description="官方文号或出处")
    promulgated_by: str = Field(description="发布机关")
    promulgated_date: str = Field(description="发布日期")
    effective_date: str = Field(description="施行日期")
    articles_range: Optional[str] = Field(default=None, description="条文范围（如 50-64）")
    articles_count: Optional[int] = Field(default=None, description="条文总数")
    chapter: Optional[str] = Field(default=None, description="章节名")
    scope_domains: list[str] = Field(default_factory=list, description="适用范围（标签）")
    key_concepts: list[str] = Field(default_factory=list, description="核心概念/关键词")
    source_url: str = Field(description="官方来源URL")
    source_type: str = Field(default="official", description="来源类型")
    retrieved_on: str = Field(description="抓取日期（YYYY-MM-DD）")
    verified_against_primary: bool = Field(default=False, description="是否已校对官方原文")
    language: str = Field(default="zh-CN")
    amendments: Optional[list[str]] = Field(default=None, description="历次修正记录")
    chapters: Optional[list[str]] = Field(default=None, description="章节列表")
    notes: str = Field(default="", description="备注说明")
