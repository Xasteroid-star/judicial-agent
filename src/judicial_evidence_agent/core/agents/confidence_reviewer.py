"""置信度审查 Agent — architecture.md §5.7, §7

动态计算多维度置信度。各维度值从上游 Agent 产出中提取，
不再使用硬编码常数。
"""

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext


class ConfidenceReviewerAgent(BaseAgent):
    """置信度审查 Agent。

    职责：
    1. 从检索结果、证据链、要素中提取各维度信号
    2. 加权计算最终置信度
    3. 按阈值分类
    """

    name = "confidence_reviewer"

    WEIGHTS = {
        "来源可信度": 0.20,
        "解析质量": 0.15,
        "要素抽取置信度": 0.15,
        "检索命中质量": 0.15,
        "图谱支撑强度": 0.20,
        "一致性评分": 0.10,
        "模型自检评分": 0.05,
    }

    THRESHOLDS = [
        (0.85, "pass", "可进入报告"),
        (0.70, "review", "需人工复核"),
        (0.50, "uncertain", "存疑或需补证"),
        (0.00, "reject", "不得作为证据链结论"),
    ]

    async def run(self, ctx: AgentContext) -> AgentContext:
        # 1. 来源可信度
        chunk_count = len(ctx.retrieved_chunks)
        # 若无 chunk，从证据链中反推支持度
        total_support = sum(
            len(c.get("supporting_evidence", [])) for c in ctx.evidence_chains
        )
        if chunk_count >= 1:
            distances = [
                c.get("distance", 1.0) for c in ctx.retrieved_chunks
                if isinstance(c.get("distance"), (int, float))
            ]
            if distances:
                avg_dist = sum(distances) / len(distances)
                source_cred = max(0.30, 0.95 - avg_dist * 0.3)
            else:
                source_cred = 0.30 + min(chunk_count * 0.10, 0.40)
        elif total_support >= 1:
            # 从 case_context 解析到了证据
            source_cred = min(0.30 + total_support * 0.12, 0.85)
        else:
            source_cred = 0.30

        # 2. 解析质量：支撑证据数 + chunk 多样性
        parse_quality = min(0.4 + total_support * 0.05, 0.95)

        # 3. 要素抽取置信度：从元素数推断，元素数越少 → 越不确定
        elem_count = len(ctx.extracted_elements)
        elem_confs = [e.get("confidence", 0.7) for e in ctx.extracted_elements]
        extraction_conf = (
            (sum(elem_confs) / len(elem_confs)) * min(elem_count / 5, 1.0)
            if elem_confs else 0.30
        )

        # 4. 检索命中质量：chunk 数 + 多样性
        unique_content = len(set(
            c.get("content", "")[:80] for c in ctx.retrieved_chunks
        ))
        total_retrieved = max(len(ctx.retrieved_chunks), 1)
        retrieval_quality = min(0.30 + (unique_content / total_retrieved) * (total_retrieved / 5) * 0.50, 0.95)

        # 5. 图谱支撑强度：节点数和边数
        edge_count = len(ctx.graph_edges)
        node_count = len(ctx.graph_nodes)
        graph_support = (
            0.85 if edge_count >= 6
            else 0.65 if edge_count >= 4
            else 0.45 if edge_count >= 2
            else 0.25
        )

        # 6. 一致性：证据链中 pass 比例 + 缺失证据数
        pass_count = sum(
            1 for c in ctx.evidence_chains if c.get("status") == "pass"
        )
        total_chains = max(len(ctx.evidence_chains), 1)
        avg_missing = sum(
            len(c.get("missing_evidence", [])) for c in ctx.evidence_chains
        ) / total_chains
        # pass 链多 + 缺失少 = 高一致性
        consistency = (pass_count / total_chains) * 0.7 + max(0.0, 0.3 - avg_missing * 0.05)

        # 7. 模型自检：基于前 6 维的方差
        scores = [
            source_cred, parse_quality, extraction_conf,
            retrieval_quality, graph_support, consistency,
        ]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        self_check = max(0.3, 1.0 - variance * 2.5)

        dimensions = [
            {"label": "来源可信度", "value": round(source_cred, 2), "weight": self.WEIGHTS["来源可信度"]},
            {"label": "解析质量", "value": round(parse_quality, 2), "weight": self.WEIGHTS["解析质量"]},
            {"label": "要素抽取置信度", "value": round(extraction_conf, 2), "weight": self.WEIGHTS["要素抽取置信度"]},
            {"label": "检索命中质量", "value": round(retrieval_quality, 2), "weight": self.WEIGHTS["检索命中质量"]},
            {"label": "图谱支撑强度", "value": round(graph_support, 2), "weight": self.WEIGHTS["图谱支撑强度"]},
            {"label": "一致性评分", "value": round(consistency, 2), "weight": self.WEIGHTS["一致性评分"]},
            {"label": "模型自检评分", "value": round(self_check, 2), "weight": self.WEIGHTS["模型自检评分"]},
        ]

        dimension_final = round(sum(
            d["value"] * d["weight"] for d in dimensions
        ), 4)

        # 证据量校准：证据类型多时小幅抬升，极少时小幅压低
        ev_type_count = sum(
            1 for c in ctx.evidence_chains
            for _ in c.get("supporting_evidence", [])
        )
        calibrated = dimension_final
        if ev_type_count >= 6:
            calibrated = min(dimension_final + 0.06, 0.95)
        elif ev_type_count >= 4:
            calibrated = min(dimension_final + 0.03, 0.95)
        elif ev_type_count <= 1:
            calibrated = max(dimension_final - 0.04, 0.10)

        # ── LLM 置信度融合 ──
        # 如果 EvidenceChainAgent 的 LLM 给出了置信度，优先采纳
        chain_llm_conf = None
        for c in ctx.evidence_chains:
            if c.get("llm_reasoning"):
                # 有 LLM 分析结果的链条，置信度更可信
                chain_llm_conf = c.get("confidence")
                break

        if chain_llm_conf is not None:
            # LLM 置信度占 70%，维度计算占 30%
            final = round(chain_llm_conf * 0.7 + calibrated * 0.3, 4)
        else:
            final = calibrated

        threshold = "reject"
        for t_val, t_name, _ in self.THRESHOLDS:
            if final >= t_val:
                threshold = t_name
                break

        ctx.confidence_dimensions = dimensions
        ctx.final_confidence = final
        ctx.threshold_result = threshold
        return ctx
