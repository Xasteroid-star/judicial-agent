"""知识图谱 Agent — architecture.md §5.5, §7

构建四层图谱：法律要件层 → 待证事实层 → 证据要素层 → 原始材料层。
LLM 模式下使用 DeepSeek 识别实体和关系，规则引擎作为 fallback。
"""

import json
import re

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext

LLM_SYSTEM_PROMPT = """你是司法知识图谱构建专家。从案件描述和要素中提取实体和关系。

图谱结构：
- LegalElement（法律要件）：罪名、法条
- Person（人物）：被告人、被害人、证人
- Fact（事实）：关键行为、情节
- Evidence（证据）：具体证据项
- Risk（风险点）：争议、冲突

关系类型：法律要件、关联于、证明、补强、冲突

你必须仅返回 JSON：
{
  "nodes": [
    {"id": "le-1", "label": "故意伤害罪(刑法第234条)", "type": "LegalElement"},
    {"id": "p-1", "label": "张三", "type": "Person"},
    {"id": "fact-1", "label": "持刀刺伤", "type": "Fact", "confidence": 0.90},
    {"id": "ev-1", "label": "监控录像", "type": "Evidence"}
  ],
  "edges": [
    {"from": "le-1", "to": "fact-1", "relation": "法律要件", "confidence": 0.95},
    {"from": "ev-1", "to": "fact-1", "relation": "证明", "confidence": 0.85}
  ]
}"""


class KnowledgeGraphAgent(BaseAgent):
    """知识图谱构建 Agent — LLM 语义构建 + 规则 fallback。"""

    name = "knowledge_graph"

    def __init__(self, llm_client=None):
        self.llm = llm_client

    # ── 罪名关键词映射 ──
    _CHARGE_ARTICLE_MAP = {
        "故意伤害": "刑法第234条", "故意杀人": "刑法第232条",
        "盗窃": "刑法第264条", "诈骗": "刑法第266条",
        "抢劫": "刑法第263条", "交通肇事": "刑法第133条",
        "贪污": "刑法第382条", "受贿": "刑法第385条",
        "帮助信息网络犯罪活动": "刑法第287条之二",
        "开设赌场": "刑法第303条", "非法经营": "刑法第225条",
        "侵犯公民个人信息": "刑法第253条之一", "侵犯著作权": "刑法第217条",
        "走私贩卖运输制造毒品": "刑法第347条",
        "非法吸收公众存款": "刑法第176条",
    }

    @staticmethod
    def _extract_charge(text: str, case_name: str) -> dict:
        m = re.search(r"构成(\S{2,8}罪)", text)
        if m:
            name = m.group(1)
            article = KnowledgeGraphAgent._CHARGE_ARTICLE_MAP.get(
                name.replace("罪", ""), "刑法相关条文")
            return {"name": name, "article": article, "label": f"{name}({article})"}
        m = re.search(r"(\S{2,6}罪)案?", case_name)
        if m:
            name = m.group(1)
            article = KnowledgeGraphAgent._CHARGE_ARTICLE_MAP.get(
                name.replace("罪", ""), "刑法相关条文")
            return {"name": name, "article": article, "label": f"{name}({article})"}
        for kw, article in KnowledgeGraphAgent._CHARGE_ARTICLE_MAP.items():
            if kw in text:
                return {"name": kw + "罪", "article": article, "label": f"{kw}罪({article})"}
        return {"name": "待确定罪名", "article": "", "label": "待确定罪名"}

    async def run(self, ctx: AgentContext) -> AgentContext:
        text = ctx.case_context or ""
        elements = ctx.extracted_elements

        if self.llm:
            try:
                graph = await self._build_with_llm(text, elements)
            except Exception:
                graph = self._build_by_rules(text, ctx)
        else:
            graph = self._build_by_rules(text, ctx)

        ctx.graph_nodes = graph.get("nodes", [])
        ctx.graph_edges = graph.get("edges", [])
        return ctx

    # ══ LLM 图谱构建 ══

    async def _build_with_llm(self, text: str, elements: list[dict]) -> dict:
        elems_text = "\n".join(
            f"- [{e['category']}] {e['value']} (conf={e['confidence']:.2f})"
            for e in elements[:10]
        )
        raw = await self.llm.generate(
            prompt=f"案件描述：{text[:1200]}\n\n已抽取要素：\n{elems_text}\n\n请构建知识图谱。仅返回 JSON：",
            system=LLM_SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.1,
        )
        return self._parse_llm_json(raw)

    @staticmethod
    def _parse_llm_json(raw: str) -> dict:
        for attempt in [
            lambda: json.loads(raw),
            lambda: json.loads(re.search(r'\{[\s\S]*\}', raw).group(0)),
            lambda: json.loads(raw.split("```json")[1].split("```")[0]) if "```json" in raw else {},
            lambda: json.loads(raw.split("```")[1].split("```")[0]) if "```" in raw else {},
        ]:
            try:
                result = attempt()
                if result and isinstance(result, dict):
                    return result
            except Exception:
                continue
        return {"nodes": [], "edges": []}

    # ══ 规则 fallback ══

    @staticmethod
    def _build_by_rules(text: str, ctx: AgentContext) -> dict:
        charge = KnowledgeGraphAgent._extract_charge(text, ctx.case_name)

        nodes = []
        edges = []

        # 法律要件节点
        legal_id = "le-charge"
        nodes.append({"id": legal_id, "label": charge["label"], "type": "LegalElement"})

        # 人物节点
        person_names = []
        for e in ctx.extracted_elements:
            if e["category"] == "人物" and e.get("value"):
                for name in e["value"].split("、"):
                    name = name.strip()
                    if name and name not in person_names:
                        person_names.append(name)
                        nodes.append({"id": f"p-{name}", "label": name, "type": "Person"})

        # 证据节点
        ev_ids = []
        evidence_kw = {"监控录像": "视听资料", "DNA": "鉴定意见", "鉴定": "鉴定意见",
                       "证人": "证人证言", "被害人陈述": "被害人陈述", "口供": "犯罪嫌疑人供述",
                       "匕首": "物证", "刀具": "物证", "银行流水": "电子数据",
                       "微信": "电子数据", "聊天记录": "电子数据"}
        for kw, ev_type in evidence_kw.items():
            if kw in text:
                eid = f"ev-{kw}"
                ev_ids.append(eid)
                nodes.append({"id": eid, "label": f"{ev_type}: {kw}", "type": "Evidence"})

        # 事实节点和 relation 边
        fact_text = text[:80] if len(text) > 20 else "案件事实"
        fact_id = "fact-0"
        nodes.append({"id": fact_id, "label": fact_text, "type": "Fact", "confidence": 0.70})

        edges.append({"from": legal_id, "to": fact_id, "relation": "法律要件", "confidence": 0.90})

        for pname in person_names:
            if pname in text:
                edges.append({"from": f"p-{pname}", "to": fact_id, "relation": "关联于", "confidence": 0.85})

        for eid in ev_ids[:5]:
            edges.append({"from": eid, "to": fact_id, "relation": "证明", "confidence": 0.75})

        # 争议/风险节点
        for e in ctx.extracted_elements:
            if e["category"] == "争议焦点" and e.get("value"):
                rid = f"risk-{e['value']}"
                nodes.append({"id": rid, "label": e["value"], "type": "Risk",
                              "confidence": e.get("confidence", 0.5)})
                edges.append({"from": rid, "to": fact_id, "relation": "冲突",
                              "confidence": e.get("confidence", 0.5)})

        return {"nodes": nodes, "edges": edges}
