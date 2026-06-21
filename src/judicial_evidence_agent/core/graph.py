"""Graph operations — 知识图谱构建与分析。

用 PostgreSQL 关系表存储节点和边，networkx 做内存中的图计算。
不依赖专门的图数据库。参考 architecture.md §5.5-5.6。
"""

from typing import Optional
from uuid import UUID

import networkx as nx

from judicial_evidence_agent.core.contracts import (
    GraphEdge,
    GraphNode,
    NodeType,
    RelationType,
    ReviewStatus,
)


class EvidenceGraph:
    """证据知识图谱 — networkx 上的有向图封装。

    四层结构（architecture.md §5.5）：
        法律要件层 -> 待证事实层 -> 证据要素层 -> 原始材料层

    使用方式：
        g = EvidenceGraph()
        g.add_node(node)
        g.add_edge(edge)
        paths = g.find_paths(from_id, to_id)
        conflicts = g.find_conflicts(case_id)
    """

    def __init__(self):
        self._g = nx.DiGraph()

    # ---- 节点 ----

    def add_node(self, node: GraphNode) -> None:
        self._g.add_node(
            str(node.node_id),
            node_type=node.node_type.value,
            label=node.label,
            properties=node.properties,
            case_id=str(node.case_id) if node.case_id else None,
            review_status=node.human_review_status.value,
            **node.properties,
        )

    def remove_node(self, node_id: UUID) -> None:
        self._g.remove_node(str(node_id))

    def get_node(self, node_id: UUID) -> Optional[dict]:
        try:
            return self._g.nodes[str(node_id)]
        except KeyError:
            return None

    # ---- 边 ----

    def add_edge(self, edge: GraphEdge) -> None:
        self._g.add_edge(
            str(edge.from_node),
            str(edge.to_node),
            relation_type=edge.relation_type.value,
            confidence=edge.confidence,
            human_review_status=edge.human_review_status.value,
        )

    def remove_edge(self, from_id: UUID, to_id: UUID) -> None:
        self._g.remove_edge(str(from_id), str(to_id))

    # ---- 查询 ----

    def find_paths(
        self, from_id: UUID, to_id: UUID, max_depth: int = 5
    ) -> list[list[str]]:
        """查找两节点间的所有证据链路径"""
        try:
            return list(
                nx.all_simple_paths(self._g, str(from_id), str(to_id), cutoff=max_depth)
            )
        except nx.NodeNotFound:
            return []

    def find_conflicts(self) -> list[tuple[str, str, dict]]:
        """返回所有冲突边"""
        return [
            (u, v, d)
            for u, v, d in self._g.edges(data=True)
            if d.get("relation_type") == RelationType.CONFLICTS.value
        ]

    def find_refutations(self) -> list[tuple[str, str, dict]]:
        """返回所有反驳边"""
        return [
            (u, v, d)
            for u, v, d in self._g.edges(data=True)
            if d.get("relation_type") == RelationType.REFUTES.value
        ]

    def neighbors(self, node_id: UUID, depth: int = 1) -> set[str]:
        """获取节点的邻居"""
        nodes = {str(node_id)}
        for _ in range(depth):
            frontier = set()
            for n in nodes:
                frontier.update(self._g.predecessors(n))
                frontier.update(self._g.successors(n))
            nodes.update(frontier)
        return nodes - {str(node_id)}

    def weak_points(self, threshold: float = 0.5) -> list[str]:
        """识别证据链薄弱环节：入度低 + 边置信度低的节点"""
        weak = []
        for node_id in self._g.nodes:
            in_edges = list(self._g.in_edges(node_id, data=True))
            if not in_edges:
                continue
            avg_confidence = sum(
                d.get("confidence", 0.0) for _, _, d in in_edges
            ) / len(in_edges)
            if avg_confidence < threshold:
                weak.append(node_id)
        return weak

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {"id": n, **self._g.nodes[n]} for n in self._g.nodes
            ],
            "edges": [
                {"from": u, "to": v, **d} for u, v, d in self._g.edges(data=True)
            ],
        }

    @property
    def node_count(self) -> int:
        return self._g.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._g.number_of_edges()
