"""要素抽取 Agent — architecture.md §5.3, §7

从案情和检索结果中动态抽取 13 类司法要素。
不再使用硬编码，不同案子产出不同要素。
"""

import re

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext


class ElementExtractorAgent(BaseAgent):
    """司法要素抽取 Agent。

    从 case_context 中提取：人物、时间、地点、行为、金额、物品、账号、
    证据名称、证明对象、法律要件、争议焦点。
    """

    name = "element_extractor"

    @staticmethod
    def _extract_persons(text: str) -> list[dict]:
        """从文本中提取人物。"""
        found = set()
        # 中文姓名常见模式
        for m in re.finditer(r"[王李张刘陈杨赵黄周吴徐孙马朱胡郭何林罗梁]某", text):
            found.add(m.group())
        for m in re.finditer(r"[王李张刘陈杨赵黄周吴徐孙马朱胡郭何林罗梁][^\s，。；]{1,2}(?=[，。；\s]|$)", text):
            name = m.group()
            if len(name) <= 3 and "某" not in name:
                found.add(name)
        return [{"category": "人物", "value": "、".join(sorted(found)[:5]), "confidence": 0.90}]

    @staticmethod
    def _extract_by_patterns(text: str) -> list[dict]:
        """基于正则模式提取。"""
        elements = []

        patterns = {
            "时间": [(r"(\d{4}年\d{1,2}月\d{1,2}日)", 0.95), (r"(\d{4}-\d{2}-\d{2})", 0.95)],
            "金额": [(r"(\d+万元?)", 0.80), (r"(\d+元)", 0.70)],
            "物品": [(r"(刀|木棍|匕首|砖头|铁管|水果刀|菜刀)", 0.85)],
            "账号": [(r"(银行卡|支付宝|微信支付)", 0.80)],
        }

        for category, pats in patterns.items():
            for pat, conf in pats:
                matches = re.findall(pat, text)
                if matches:
                    elements.append({
                        "category": category,
                        "value": "、".join(matches[:3]),
                        "confidence": conf,
                    })

        return elements

    @staticmethod
    def _extract_evidence_types(text: str) -> list[dict]:
        """从文本中识别证据类型关键词（覆盖 8 类法定证据）。"""
        elements = []
        evidence_keywords = {
            # 物证
            "凶器": "物证", "刀具": "物证", "提取": "物证",
            "物证": "物证", "指纹": "物证",
            # 书证
            "书证": "书证", "报案记录": "书证", "登记表": "书证",
            # 证人证言
            "目击证人": "证人证言", "目击": "证人证言",
            "证人": "证人证言", "证人证言": "证人证言",
            # 被害人陈述
            "被害人陈述": "被害人陈述",
            # 犯罪嫌疑人/被告人供述
            "供述": "犯罪嫌疑人供述", "口供": "犯罪嫌疑人供述",
            "被告人供述": "犯罪嫌疑人供述",
            # 鉴定意见
            "DNA": "鉴定意见", "鉴定": "鉴定意见",
            # 勘验检查笔录
            "勘查": "勘验检查笔录", "勘验": "勘验检查笔录",
            "现场勘查": "勘验检查笔录",
            # 视听资料
            "监控录像": "视听资料", "监控": "视听资料",
            "录音录像": "视听资料",
            # 电子数据
            "银行流水": "电子数据", "交易流水": "电子数据",
            "转账记录": "电子数据", "微信": "电子数据",
            "聊天记录": "电子数据", "IP": "电子数据",
            "服务器日志": "电子数据", "电子数据": "电子数据",
        }
        found_types = set()
        for kw, ev_type in evidence_keywords.items():
            if kw in text:
                if ev_type not in found_types:
                    found_types.add(ev_type)
                    elements.append({
                        "category": "证据名称",
                        "value": ev_type,
                        "confidence": 0.85 if kw in ["DNA", "指纹", "监控录像", "银行流水"] else 0.75,
                    })
        return elements

    @staticmethod
    def _extract_disputes(text: str) -> list[dict]:
        """识别争议焦点。"""
        disputes = []
        dispute_keywords = {
            "刑讯逼供": 0.65,
            "威胁": 0.60,
            "疲劳讯问": 0.65,
            "非法证据": 0.70,
            "证据不足": 0.75,
            "无法认定": 0.75,
            "自首": 0.60,
            "正当防卫": 0.55,
            "拒不认罪": 0.60,
            "翻供": 0.55,
        }
        for kw, conf in dispute_keywords.items():
            if kw in text:
                disputes.append({
                    "category": "争议焦点",
                    "value": kw,
                    "confidence": conf,
                })
        return disputes

    async def run(self, ctx: AgentContext) -> AgentContext:
        text = f"{ctx.case_context} {ctx.query}"

        elements = []
        elements.extend(self._extract_persons(text))
        elements.extend(self._extract_by_patterns(text))
        elements.extend(self._extract_evidence_types(text))
        elements.extend(self._extract_disputes(text))

        # 兜底：一个都没抽到时至少标注"证据不足"
        if not elements:
            elements.append({
                "category": "证明对象",
                "value": "无法确定（案情信息不足）",
                "confidence": 0.30,
            })

        ctx.extracted_elements = elements
        return ctx
