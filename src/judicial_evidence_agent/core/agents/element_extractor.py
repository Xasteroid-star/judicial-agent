"""要素抽取 Agent — architecture.md §5.3, §7

从案情中抽取司法要素。LLM 模式使用 DeepSeek 进行语义提取，正则作为 fallback。
"""

import json
import re

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext

LLM_SYSTEM_PROMPT = """你是司法要素抽取专家。从案件描述中提取结构化要素。

提取维度：
1. 人物（被告人、被害人、证人等）
2. 时间（案发时间）
3. 地点（案发地点）
4. 行为（犯罪手段、方式）
5. 金额/数量（涉案金额、数量）
6. 物品（作案工具、涉案物品）
7. 证据名称（物证、书证、鉴定意见等法定证据类型）
8. 争议焦点（正当防卫、非法证据、翻供、自首等）
9. 法律要件（罪名构成要件）

你必须仅返回 JSON：
{
  "elements": [
    {"category": "人物", "value": "张三", "confidence": 0.95},
    {"category": "时间", "value": "2024年3月", "confidence": 0.90},
    {"category": "证据名称", "value": "监控录像", "confidence": 0.85}
  ]
}"""


class ElementExtractorAgent(BaseAgent):
    """司法要素抽取 Agent — LLM 语义提取 + 正则 fallback。"""

    name = "element_extractor"

    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def run(self, ctx: AgentContext) -> AgentContext:
        text = f"{ctx.case_context} {ctx.query}"

        if self.llm:
            try:
                elements = await self._extract_with_llm(text)
            except Exception:
                elements = self._extract_by_rules(text)
        else:
            elements = self._extract_by_rules(text)

        if not elements:
            elements.append({
                "category": "证明对象",
                "value": "无法确定（案情信息不足）",
                "confidence": 0.30,
            })

        ctx.extracted_elements = elements
        return ctx

    # ══ LLM 提取 ══

    async def _extract_with_llm(self, text: str) -> list[dict]:
        raw = await self.llm.generate(
            prompt=f"请从以下案件描述中提取司法要素：\n\n{text[:1500]}\n\n请仅返回 JSON：",
            system=LLM_SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.1,
        )
        return self._parse_llm_json(raw)

    @staticmethod
    def _parse_llm_json(raw: str) -> list[dict]:
        for attempt in [
            lambda: json.loads(raw).get("elements", []),
            lambda: json.loads(re.search(r'\{[\s\S]*\}', raw).group(0)).get("elements", []),
            lambda: json.loads(raw.split("```json")[1].split("```")[0]).get("elements", []) if "```json" in raw else [],
            lambda: json.loads(raw.split("```")[1].split("```")[0]).get("elements", []) if "```" in raw else [],
        ]:
            try:
                result = attempt()
                if result:
                    return result
            except Exception:
                continue
        return []

    # ══ 正则 fallback ══

    @staticmethod
    def _extract_by_rules(text: str) -> list[dict]:
        elements = []

        # 人物
        found = set()
        for m in re.finditer(r"[王李张刘陈杨赵黄周吴徐孙马朱胡郭何林罗梁]某", text):
            found.add(m.group())
        for m in re.finditer(r"[王李张刘陈杨赵黄周吴徐孙马朱胡郭何林罗梁][^\s，。；]{1,2}(?=[，。；\s]|$)", text):
            name = m.group()
            if len(name) <= 3 and "某" not in name:
                found.add(name)
        if found:
            elements.append({"category": "人物", "value": "、".join(sorted(found)[:5]), "confidence": 0.90})

        # 时间
        for pat, conf in [(r"(\d{4}年\d{1,2}月\d{1,2}日)", 0.95), (r"(\d{4}年\d{1,2}月)", 0.85)]:
            matches = re.findall(pat, text)
            if matches:
                elements.append({"category": "时间", "value": "、".join(matches[:3]), "confidence": conf})
                break

        # 金额
        for pat, conf in [(r"(\d+万\s*元)", 0.85), (r"(\d+元)", 0.70)]:
            matches = re.findall(pat, text)
            if matches:
                elements.append({"category": "金额", "value": "、".join(matches[:3]), "confidence": conf})
                break

        # 地点
        locs = re.findall(r"[一-鿿]{2,4}(?:市|区|县|街道|小区)", text)
        if locs:
            elements.append({"category": "地点", "value": "、".join(locs[:3]), "confidence": 0.85})

        # 证据类型
        evidence_kw = {
            "监控录像": "视听资料", "DNA": "鉴定意见", "鉴定": "鉴定意见",
            "证人证言": "证人证言", "被害人陈述": "被害人陈述",
            "供述": "犯罪嫌疑人供述", "口供": "犯罪嫌疑人供述",
            "匕首": "物证", "刀具": "物证", "凶器": "物证",
            "银行流水": "电子数据", "微信": "电子数据", "聊天记录": "电子数据",
        }
        found_types = set()
        for kw, ev in evidence_kw.items():
            if kw in text and ev not in found_types:
                found_types.add(ev)
                elements.append({"category": "证据名称", "value": ev, "confidence": 0.80})

        # 争议焦点
        disputes = {"刑讯逼供": 0.65, "威胁": 0.60, "非法证据": 0.70,
                     "证据不足": 0.75, "正当防卫": 0.65, "翻供": 0.60, "自首": 0.65}
        for kw, conf in disputes.items():
            if kw in text:
                elements.append({"category": "争议焦点", "value": kw, "confidence": conf})

        return elements
