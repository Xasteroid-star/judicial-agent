"""人工复核 Agent — architecture.md §7

接收人工修改，反向更新图谱和样本。
生成复核项列表，记录确认/驳回操作。
"""

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext


class HumanReviewAgent(BaseAgent):
    """人工复核 Agent。

    职责：
    1. 生成待复核项列表
    2. 接收确认/驳回操作
    3. 反向更新图谱和评测样本
    """

    name = "human_review"

    async def run(self, ctx: AgentContext) -> AgentContext:
        items = []

        # 证据链中置信度在 0.50-0.85 之间的项
        for chain in ctx.evidence_chains:
            if chain["status"] == "review":
                items.append({
                    "review_id": f"RV-CH-{chain['chain_id']}",
                    "type": "evidence_chain",
                    "title": f"证据链审查：{chain['fact_to_prove']}",
                    "detail": f"置信度 {chain['confidence']:.2f}，需人工判断支撑证据是否充分。",
                    "confidence": chain["confidence"],
                    "status": "pending",
                })

        # 冲突项
        for conflict in ctx.conflicts:
            items.append({
                "review_id": f"RV-CF-{conflict['type']}",
                "type": "conflict",
                "title": conflict["claim_a"],
                "detail": f"对立方：{conflict['claim_b']}\n建议：{conflict['resolution']}",
                "confidence": 0.5,
                "status": "pending",
            })

        # 要素中置信度 < 0.70 的
        for e in ctx.extracted_elements:
            if e["confidence"] < 0.70:
                items.append({
                    "review_id": f"RV-EL-{e['category']}",
                    "type": "element",
                    "title": f"要素审查：{e['category']}={e['value']}",
                    "detail": f"抽取置信度仅 {e['confidence']:.2f}，建议人工核实。",
                    "confidence": e["confidence"],
                    "status": "pending",
                })

        ctx.review_items = items
        ctx.review_status = "pending" if items else "pass"
        return ctx
