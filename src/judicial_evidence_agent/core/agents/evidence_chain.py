"""证据链分析 Agent — architecture.md §5.8, §7

基于检索到的法条和证据，动态构建证据链。
当 RAG 检索无结果时，直接从 case_context 文本中解析证据。
LLM 模式下使用 DeepSeek 进行语义分析，规则引擎作为 fallback。
"""

import json
import re
from typing import Optional

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext

# ── 证据类型关键词映射（从 case_context 直接解析，LLM 不可用时的 fallback） ──
EVIDENCE_KW_MAP = {
    "监控录像": "视听资料", "监控": "视听资料", "录音录像": "视听资料",
    "DNA": "鉴定意见", "鉴定": "鉴定意见", "司法鉴定": "鉴定意见",
    "目击证人": "证人证言", "证人": "证人证言", "证人证言": "证人证言",
    "被害人陈述": "被害人陈述", "被害人": "被害人陈述",
    "供述": "犯罪嫌疑人供述", "口供": "犯罪嫌疑人供述", "被告人供述": "犯罪嫌疑人供述",
    "凶器": "物证", "物证": "物证", "刀具": "物证", "提取": "物证",
    "勘验": "勘验检查笔录", "勘查": "勘验检查笔录", "现场勘查": "勘验检查笔录",
    "银行流水": "电子数据", "交易流水": "电子数据", "转账记录": "电子数据",
    "微信": "电子数据", "聊天记录": "电子数据",
    "IP": "电子数据", "服务器日志": "电子数据", "日志": "电子数据",
    "书证": "书证", "报案记录": "书证",
    "指纹": "物证",
}

# ── 法条引用模式 ──
LAW_QUOTE_PATTERNS = [
    (r"刑诉法第(\d+条)", "刑事诉讼法"),
    (r"刑事诉讼法第(\d+条)", "刑事诉讼法"),
    (r"刑法第(\d+条)", "刑法"),
    (r"口供.*补强", "刑诉法第55条（口供补强规则）"),
    (r"非法证据", "刑诉法第56条（非法证据排除）"),
    (r"电子数据", "电子数据规定"),
]

# ── LLM 分析 System Prompt ──
LLM_SYSTEM_PROMPT = """你是中国刑事证据审查专家，精通《刑事诉讼法》证据规则。

你的任务：分析案件材料，输出结构化的证据链分析结果。

原则：
1. 从案件描述中识别所有证据类型（法定 8 类：物证、书证、证人证言、被害人陈述、犯罪嫌疑人/被告人供述和辩解、鉴定意见、勘验检查笔录、视听资料/电子数据）
2. 判断证据链完整性（chain_status）：
   - pass：证据种类 >= 3 且互相印证，或多种电子证据（流水/聊天/IP/日志）独立形成闭环
   - review：证据基本充分但有需核实之处（如非法证据主张、讯问录音缺失）
   - reject：仅口供无实物证据，或证据种类 < 2 且无补强可能
3. 口供不能单独定案（刑诉法第55条）；仅口供+无实物证据 → reject
4. 电子数据规则：银行流水+微信记录+IP日志+服务器日志等多种电子证据互相印证时，即使无口供也可认定事实完整，chain_status=pass
5. 非法证据主张（如辩称遭威胁、录音录像缺失）≠ 证据链不完整：若有客观证据（流水/记录/陈述），chain_status仍为pass或review，但confidence应下调
6. 给出 0.00-1.00 的置信度：>=0.85 为确实充分，0.70-0.85 需复核，<0.70 存疑或驳回

你必须**仅返回**如下 JSON（不要有其他文字）：
{
  "evidence_types": ["证据类型1", "证据类型2"],
  "chain_status": "pass",
  "missing_evidence": ["缺失项或空"],
  "confidence": 0.85,
  "reasoning": "简要分析理由，包含引用的法条"
}"""


class EvidenceChainAgent(BaseAgent):
    """证据链分析 Agent — 双重证据源（LLM 语义分析 + 规则 fallback）。"""

    name = "evidence_chain"

    def __init__(self, llm_client=None):
        self.llm = llm_client

    # ═══════════════════════════════════════════════
    # Rule-based fallback（保持原有逻辑）
    # ═══════════════════════════════════════════════

    @staticmethod
    def _parse_evidence_from_text(text: str) -> dict[str, list[dict]]:
        """从案件文本直接解析证据项（不依赖 RAG / LLM）。"""
        evidence_by_type: dict[str, list[dict]] = {}
        e_data_subs = {
            "银行流水": "电子数据(流水)", "交易流水": "电子数据(流水)",
            "转账记录": "电子数据(流水)",
            "微信": "电子数据(通讯)", "聊天记录": "电子数据(通讯)",
            "IP": "电子数据(日志)", "服务器日志": "电子数据(日志)",
            "日志": "电子数据(日志)",
        }
        for kw, etype in EVIDENCE_KW_MAP.items():
            if kw in text:
                actual_type = e_data_subs.get(kw, etype)
                if actual_type not in evidence_by_type:
                    evidence_by_type[actual_type] = []
                evidence_by_type[actual_type].append({
                    "type": actual_type,
                    "content": f"{text[:80]}...",
                    "confidence": 0.80 if kw in ["DNA", "监控录像", "银行流水", "交易流水"] else 0.70,
                    "chunk_id": f"parsed-{actual_type}",
                })
        return evidence_by_type

    @staticmethod
    def _parse_law_refs(text: str) -> list[dict]:
        laws = []
        for pat, law_name in LAW_QUOTE_PATTERNS:
            m = re.search(pat, text)
            if m:
                article = m.group(0) if m.groups() else m.group(0)
                laws.append({"name": law_name, "content": article, "date": ""})
        seen = set()
        uniq = []
        for l in laws:
            if l["content"] not in seen:
                seen.add(l["content"])
                uniq.append(l)
        return uniq

    # ═══════════════════════════════════════════════
    # LLM 语义分析
    # ═══════════════════════════════════════════════

    async def _llm_analysis(self, ctx: AgentContext) -> Optional[dict]:
        """调用 DeepSeek 进行语义分析，返回结构化结果。"""
        if not self.llm:
            return None

        prompt = f"""请分析以下案件材料：

案件描述：{ctx.case_context}
评估问题：{ctx.query}

分析要求：
1. 从描述中识别所有证据类型（法定 8 类）
2. 判断证据链是否完整
3. 列出缺失的关键证据（如有）
4. 给出置信度评分

请仅返回 JSON："""

        try:
            raw = await self.llm.generate(
                prompt=prompt,
                system=LLM_SYSTEM_PROMPT,
                max_tokens=1024,
                temperature=0.1,
            )
            # 提取 JSON（DeepSeek 可能在代码块中返回）
            return self._parse_llm_json(raw)
        except Exception:
            return None

    @staticmethod
    def _parse_llm_json(raw: str) -> Optional[dict]:
        """从 LLM 返回文本中提取 JSON。"""
        # 尝试直接解析
        for attempt in [
            lambda: json.loads(raw),
            lambda: json.loads(re.search(r'\{[\s\S]*\}', raw).group(0)),
            lambda: json.loads(raw.split("```json")[1].split("```")[0])
            if "```json" in raw else None,
            lambda: json.loads(raw.split("```")[1].split("```")[0])
            if "```" in raw else None,
        ]:
            try:
                result = attempt()
                if result:
                    return result
            except Exception:
                continue
        return None

    # ═══════════════════════════════════════════════
    # Main
    # ═══════════════════════════════════════════════

    async def run(self, ctx: AgentContext) -> AgentContext:
        # ── Phase 1: LLM 语义分析（主力） ──
        llm_result = await self._llm_analysis(ctx)

        # ── Phase 2: 规则解析（作为 fallback / 补充详细信息）──
        evidence_by_type: dict[str, list[dict]] = {}

        # RAG chunks
        for c in ctx.retrieved_chunks:
            etype = c.get("evidence_type", "") or "其他"
            if etype not in evidence_by_type:
                evidence_by_type[etype] = []
            evidence_by_type[etype].append({
                "type": etype,
                "content": c.get("content_preview", "") or c.get("content", "")[:120],
                "confidence": c.get("confidence", 0.5),
                "chunk_id": c["chunk_id"],
            })

        # 文本解析
        parsed = self._parse_evidence_from_text(ctx.case_context or "")
        parsed.update(self._parse_evidence_from_text(ctx.query or ""))
        for etype, evs in parsed.items():
            if etype not in evidence_by_type:
                evidence_by_type[etype] = evs

        # 法条
        laws = []
        for s in ctx.retrieved_statutes:
            laws.append({
                "name": s.get("law_name", ""),
                "date": s.get("effective_date", ""),
                "content": s["content"][:200],
            })
        text_laws = self._parse_law_refs(
            (ctx.case_context or "") + " " + (ctx.query or "")
        )
        laws.extend(text_laws)

        # ── Phase 3: 合并结果 ──
        total_evidence_types = len(evidence_by_type)
        strong_types = sum(
            1 for evs in evidence_by_type.values()
            for ev in evs if ev.get("confidence", 0) >= 0.75
        )

        # 电子证据子类型计数
        electronic_strong = 0
        for etype, evs in evidence_by_type.items():
            if "电子数据" in etype:
                for ev in evs:
                    if isinstance(ev, dict) and ev.get("confidence", 0) >= 0.75:
                        electronic_strong += 1

        # 不足提示词
        insufficiency_hints = sum(
            1 for hint in ["仅有", "没有", "无", "缺少", "缺失", "不足"]
            if hint in (ctx.query or "") or hint in (ctx.case_context or "")
        )

        if llm_result:
            # 使用 LLM 的判断结果
            chain_status = llm_result.get("chain_status", "review")
            llm_confidence = float(llm_result.get("confidence", 0.5))
            llm_missing = llm_result.get("missing_evidence", [])
            llm_reasoning = llm_result.get("reasoning", "")
            llm_evidence_types = llm_result.get("evidence_types", [])
        else:
            # 规则 fallback
            chain_status = "review"
            llm_confidence = None
            llm_missing = []
            llm_reasoning = ""
            llm_evidence_types = []

        # Fallback: 如果 LLM 未返回，使用规则判断
        if not llm_result:
            if total_evidence_types >= 3 and strong_types >= 3:
                chain_status = "pass"
            elif total_evidence_types >= 3 and electronic_strong >= 3:
                chain_status = "pass"
            elif total_evidence_types >= 2 and strong_types >= 2:
                chain_status = "pass"
            elif total_evidence_types >= 2 and (strong_types >= 1 or electronic_strong >= 2):
                chain_status = "review" if insufficiency_hints >= 2 else "pass"
            elif total_evidence_types >= 2 and strong_types >= 1:
                chain_status = "review"
            elif strong_types >= 1:
                chain_status = "review"
            else:
                chain_status = "reject"

        # 规则缺失证据（LLM 缺失优先）
        missing = llm_missing if llm_missing else []
        if not missing:
            if chain_status == "review":
                missing = ["补充证据种类", "核实证据来源"]
            elif chain_status == "reject":
                missing = ["证据严重不足", "需调取原始材料", "建议补充侦查"]

        # 置信度：LLM 优先级最高，否则规则计算
        if llm_confidence is not None:
            chain_confidence = max(0.10, min(0.98, llm_confidence))
        else:
            chain_confidence = round(
                0.35 + min(total_evidence_types * 0.08, 0.32)
                + min(strong_types * 0.08, 0.16)
                + min(electronic_strong * 0.04, 0.08)
                - min(insufficiency_hints * 0.08, 0.16),
                2,
            )
            chain_confidence = max(0.15, min(0.95, chain_confidence))

        # 构建支撑证据列表
        all_evidence = []
        for etype, evs in evidence_by_type.items():
            all_evidence.extend(evs[:1])

        # 待证事实
        fact_elements = {
            e["value"]: e["confidence"]
            for e in ctx.extracted_elements
            if e["category"] in ("证明对象", "行为", "证据名称")
        }
        fact_text = (
            list(fact_elements.keys())[0] if fact_elements
            else (ctx.case_context[:60] if ctx.case_context else "案件事实待确认")
        )
        legal_basis = laws[0]["name"] if laws else "刑法"

        chains = [{
            "chain_id": "EC-001",
            "legal_element": f"基于 {len(llm_evidence_types) or total_evidence_types} 类证据的综合分析",
            "fact_to_prove": fact_text,
            "supporting_evidence": all_evidence[:6],
            "legal_basis": legal_basis,
            "missing_evidence": missing,
            "confidence": chain_confidence,
            "status": chain_status,
            "llm_reasoning": llm_reasoning,
        }]

        # 冲突识别
        conflicts = []
        hi_conf = sum(
            1 for evs in evidence_by_type.values()
            for ev in evs if ev.get("confidence", 0) >= 0.75
        )
        lo_conf = sum(
            1 for evs in evidence_by_type.values()
            for ev in evs if ev.get("confidence", 0) < 0.5
        )
        if lo_conf > hi_conf:
            conflicts.append({
                "type": "证据质量参差",
                "claim_a": f"强证据 {hi_conf} 项",
                "claim_b": f"弱证据 {lo_conf} 项",
                "resolution": "核实弱证据来源，补强后再审",
                "risk_level": "高" if lo_conf > hi_conf * 2 else "中",
            })

        ctx.evidence_chains = chains
        ctx.conflicts = conflicts
        return ctx
