"""Agent 基类 + 统一上下文结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentContext:
    """在 Agent 流水线中传递的共享上下文。

    每个 Agent 读取需要的字段，写入产出字段。
    流水线结束时上下文中包含完整分析结果。
    """

    # 输入
    case_id: str = ""
    case_name: str = ""
    query: str = ""
    case_context: str = ""

    # 卷宗解析 Agent 产出
    material_ids: list[str] = field(default_factory=list)
    processing_errors: list[str] = field(default_factory=list)

    # 要素抽取 Agent 产出
    extracted_elements: list[dict] = field(default_factory=list)

    # RAG 检索 Agent 产出
    retrieved_statutes: list[dict] = field(default_factory=list)
    retrieved_chunks: list[dict] = field(default_factory=list)

    # 知识图谱 Agent 产出
    graph_nodes: list[dict] = field(default_factory=list)
    graph_edges: list[dict] = field(default_factory=list)

    # 证据链分析 Agent 产出
    evidence_chains: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)

    # 置信度审查 Agent 产出
    confidence_dimensions: list[dict] = field(default_factory=list)
    final_confidence: float = 0.0
    threshold_result: str = "pending"

    # 报告生成 Agent 产出
    report_title: str = ""
    report_sections: list[dict] = field(default_factory=list)
    report_markdown: str = ""

    # 人工复核 Agent 产出
    review_items: list[dict] = field(default_factory=list)
    review_status: str = "pending"


class BaseAgent:
    """Agent 基类。

    每个 Agent 实现 `run(ctx)` 方法，
    读取 ctx 中的输入字段，写入产出字段。
    """

    name: str = "base"

    async def run(self, ctx: AgentContext) -> AgentContext:
        """执行 Agent 逻辑，返回更新后的上下文。"""
        raise NotImplementedError
