"""知识图谱 Agent — architecture.md §5.5, §7

构建四层图谱：法律要件层 → 待证事实层 → 证据要素层 → 原始材料层。
从案件上下文和上游抽取结果中动态生成，彻底移除硬编码。
"""

import re

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext


class KnowledgeGraphAgent(BaseAgent):
    """知识图谱构建 Agent — 全动态生成。

    输入：ctx.case_context, ctx.extracted_elements, ctx.retrieved_chunks, ctx.case_name
    输出：ctx.graph_nodes, ctx.graph_edges
    """

    name = "knowledge_graph"

    # ── 罪名关键词 → 法律条文 ──
    _CHARGE_ARTICLE_MAP = {
        "挪用资金": "刑法第272条",
        "挪用公款": "刑法第384条",
        "职务侵占": "刑法第271条",
        "贪污": "刑法第382条",
        "受贿": "刑法第385条",
        "故意伤害": "刑法第234条",
        "故意杀人": "刑法第232条",
        "盗窃": "刑法第264条",
        "诈骗": "刑法第266条",
        "抢劫": "刑法第263条",
        "交通肇事": "刑法第133条",
        "危险驾驶": "刑法第133条之一",
        "非法吸收公众存款": "刑法第176条",
        "集资诈骗": "刑法第192条",
        "帮助信息网络犯罪活动": "刑法第287条之二",
        "掩饰隐瞒犯罪所得": "刑法第312条",
        "走私贩卖运输制造毒品": "刑法第347条",
        "寻衅滋事": "刑法第293条",
        "组织领导传销活动": "刑法第224条之一",
        "开设赌场": "刑法第303条",
        "非法经营": "刑法第225条",
        "侵犯公民个人信息": "刑法第253条之一",
        "侵犯著作权": "刑法第217条",
    }

    @staticmethod
    def _extract_charge(text: str, case_name: str) -> dict:
        """从案件文本提取罪名信息。"""
        # 模式1: "构成...罪"
        m = re.search(r"构成(\S{2,8}罪)", text)
        if m:
            name = m.group(1)
            article = KnowledgeGraphAgent._CHARGE_ARTICLE_MAP.get(
                name.replace("罪", ""), "刑法相关条文"
            )
            return {"name": name, "article": article, "label": f"{name}({article})"}

        # 模式2: "其行为已构成..."
        m = re.search(r"行为已构成(\S{2,8}罪)", text)
        if m:
            name = m.group(1)
            article = KnowledgeGraphAgent._CHARGE_ARTICLE_MAP.get(
                name.replace("罪", ""), "刑法相关条文"
            )
            return {"name": name, "article": article, "label": f"{name}({article})"}

        # 模式3: 从案件名提取 "XXX罪案"
        m = re.search(r"(\S{2,6}罪)案?", case_name)
        if m:
            name = m.group(1)
            article = KnowledgeGraphAgent._CHARGE_ARTICLE_MAP.get(
                name.replace("罪", ""), "刑法相关条文"
            )
            return {"name": name, "article": article, "label": f"{name}({article})"}

        # 模式4: 关键词匹配
        for kw, article in KnowledgeGraphAgent._CHARGE_ARTICLE_MAP.items():
            if kw in text:
                name = kw + "罪"
                return {"name": name, "article": article, "label": f"{name}({article})"}

        return {"name": "待确定罪名", "article": "", "label": "待确定罪名"}

    @staticmethod
    def _extract_facts(text: str) -> list[dict]:
        """从案件文本中提取关键事实节点。"""
        facts = []
        sentences = re.split(r"[。；\n]", text)

        # 金额相关事实
        amount_patterns = [
            (r"共计人民币(\d+[\d,.]*万?\s*元)", "涉案金额"),
            (r"人民币(\d+[\d,.]*万?\s*元)", "涉案金额"),
            (r"(\d+万\s*元)", "涉案金额"),
        ]
        for sent in sentences:
            for pat, label in amount_patterns:
                m = re.search(pat, sent)
                if m and len(sent) > 10:
                    facts.append({
                        "label": f"{label}: {m.group(1)}",
                        "keywords": ["元", "万", "金额", "资金"],
                        "confidence": 0.85,
                    })
                    break

        # 行为/手段事实
        action_keywords = {
            "挪用": "挪用资金",
            "侵占": "侵占财产",
            "诈骗": "诈骗行为",
            "盗窃": "盗窃行为",
            "贪污": "贪污行为",
            "受贿": "受贿行为",
            "伤害": "伤害行为",
            "殴打": "殴打行为",
            "自首": "自首情节",
            "自动投案": "自首情节",
            "赌博": "赌博非法活动",
            "网络赌博": "非法活动（网络赌博）",
        }
        seen_labels = set()
        for sent in sentences:
            if len(sent) < 10:
                continue
            for kw, label in action_keywords.items():
                if kw in sent and label not in seen_labels:
                    seen_labels.add(label)
                    facts.append({
                        "label": sent.strip()[:60],
                        "keywords": [kw] + ([w for w in re.findall(r"[一-鿿]{2,4}", sent) if len(w) >= 2][:3]),
                        "confidence": 0.75,
                    })
                    break

        # 身份/职务相关
        for sent in sentences:
            if "担任" in sent and "利用" in sent and len(sent) > 15:
                facts.append({
                    "label": sent.strip()[:60],
                    "keywords": ["担任", "利用", "职务"],
                    "confidence": 0.80,
                })
                break

        # 兜底: 至少保证一个事实
        if not facts and text:
            facts.append({
                "label": text.strip()[:60],
                "keywords": [w for w in re.findall(r"[一-鿿]{2,4}", text) if len(w) >= 2][:5],
                "confidence": 0.60,
            })

        return facts[:5]

    async def run(self, ctx: AgentContext) -> AgentContext:
        text = ctx.case_context or ""

        # ── 1. 提取罪名 ──
        charge = self._extract_charge(text, ctx.case_name)

        # ── 2. 提取事实 ──
        facts = self._extract_facts(text)

        # ── 3. 构建节点 ──
        nodes = []

        # 法律要件节点
        legal_id = "le-charge"
        nodes.append({"id": legal_id, "label": charge["label"], "type": "LegalElement"})

        # 人物节点（从要素抽取结果）
        person_names = []
        for e in ctx.extracted_elements:
            if e["category"] == "人物" and e.get("value"):
                for name in e["value"].split("、"):
                    name = name.strip()
                    if name and name not in person_names:
                        person_names.append(name)
                        nodes.append({
                            "id": f"p-{name}", "label": name, "type": "Person",
                        })

        # 事实节点
        fact_ids = []
        for i, fact in enumerate(facts):
            fid = f"fact-{i}"
            fact_ids.append(fid)
            nodes.append({
                "id": fid, "label": fact["label"], "type": "Fact",
                "confidence": fact.get("confidence", 0.7),
            })

        # 证据节点（从检索结果）
        ev_ids = []
        for i, chunk in enumerate(ctx.retrieved_chunks[:8]):
            eid = f"ev-{i}"
            ev_ids.append(eid)
            preview = (chunk.get("content_preview", "") or chunk.get("content", ""))[:40]
            etype = chunk.get("evidence_type", "") or "证据片段"
            nodes.append({
                "id": eid, "label": f"{etype}: {preview}", "type": "Evidence",
            })

        # 争议/风险节点
        risk_ids = []
        for e in ctx.extracted_elements:
            if e["category"] == "争议焦点" and e.get("value"):
                rid = f"risk-{e['value']}"
                risk_ids.append(rid)
                nodes.append({
                    "id": rid, "label": e["value"], "type": "Risk",
                    "confidence": e.get("confidence", 0.5),
                })

        # ── 4. 构建边 ──
        edges = []

        # 法律要件 → 每个事实
        for fid in fact_ids:
            edges.append({
                "from": legal_id, "to": fid, "relation": "法律要件", "confidence": 0.90,
            })

        # 人物 → 相关事实（人名出现在事实文本中）
        for pname in person_names:
            for i, fact in enumerate(facts):
                if pname in fact["label"]:
                    edges.append({
                        "from": f"p-{pname}", "to": f"fact-{i}",
                        "relation": "关联于", "confidence": 0.85,
                    })

        # 证据 → 事实（证据内容命中事实关键词）
        for i, chunk in enumerate(ctx.retrieved_chunks[:8]):
            chunk_text = chunk.get("content_preview", "") or chunk.get("content", "") or ""
            for j, fact in enumerate(facts):
                match_count = sum(
                    1 for kw in fact.get("keywords", [])
                    if kw and len(kw) >= 2 and kw in chunk_text
                )
                if match_count >= 1:
                    edges.append({
                        "from": f"ev-{i}", "to": f"fact-{j}",
                        "relation": "证明", "confidence": min(0.95, 0.65 + match_count * 0.1),
                    })

        # 证据之间的补强关系（相邻证据默认补强）
        for i in range(len(ev_ids) - 1):
            edges.append({
                "from": ev_ids[i], "to": ev_ids[i + 1],
                "relation": "补强", "confidence": 0.60,
            })

        # 争议/风险节点 → 事实/证据
        for e in ctx.extracted_elements:
            if e["category"] == "争议焦点" and e.get("value"):
                target_found = False
                for j, fact in enumerate(facts):
                    if e["value"] in fact["label"]:
                        edges.append({
                            "from": f"risk-{e['value']}", "to": f"fact-{j}",
                            "relation": "冲突", "confidence": e.get("confidence", 0.5),
                        })
                        target_found = True
                if not target_found and fact_ids:
                    # 争议与第一个事实建立弱关联
                    edges.append({
                        "from": f"risk-{e['value']}", "to": fact_ids[0],
                        "relation": "冲突", "confidence": 0.35,
                    })

        ctx.graph_nodes = nodes
        ctx.graph_edges = edges
        return ctx
