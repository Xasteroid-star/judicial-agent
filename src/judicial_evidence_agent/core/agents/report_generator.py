"""报告生成 Agent — architecture.md §5.8, §7

从流水线上游的所有 Agent 产出中生成可溯源报告。
LLM 模式下使用 DeepSeek 生成自然语言报告，模板为 fallback。
"""

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext

LLM_SYSTEM_PROMPT = """你是中国刑事证据审查专家助理，负责撰写证据链审查报告。

核心规则（不可违反）：
1. 严格基于提供的证据材料撰写，不得编造事实
2. 每个结论必须附带证据来源引用（如"鉴定意见""证人证言""物证""监控录像"等）
3. 引用相关法条（刑法、刑事诉讼法）
4. 低置信度结论必须标注"待核实"
5. 证据链分析结果中的状态和置信度必须原样保留，不得修改
6. 证据链状态为 ✗驳回 时，报告必须明确指出"证据不足""无法认定"，严禁使用"证据确实充分"
7. 行文规范，符合公诉文书风格

报告结构：
## 一、案件材料处理概况
## 二、核心证据链分析
## 三、对立证据与风险识别
## 四、置信度审查说明
## 五、补证与复核建议
## 六、主要溯源清单

请直接输出报告正文，不要输出 JSON 或其他格式。"""


class ReportGeneratorAgent(BaseAgent):
    """报告生成 Agent — LLM 生成 + 模板 fallback。"""

    name = "report_generator"

    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def run(self, ctx: AgentContext) -> AgentContext:
        from judicial_evidence_agent.core.observe import observe

        should_llm, reason, _ = observe("report_generator", ctx)

        if self.llm and should_llm:
            try:
                markdown = await self._generate_with_llm(ctx)
            except Exception:
                markdown = self._generate_template(ctx)
        else:
            markdown = self._generate_template(ctx)

        ctx.report_title = f"{ctx.case_name or '案件'} — 证据链审查报告"
        ctx.report_markdown = markdown
        ctx.report_sections = []  # sections 不再使用，保留兼容
        return ctx

    # ═══════════════════════════════════════════════
    # LLM 报告生成
    # ═══════════════════════════════════════════════

    async def _generate_with_llm(self, ctx: AgentContext) -> str:
        """调用 DeepSeek 生成自然语言报告。"""

        # 构建结构化上下文
        evidence_summary = self._build_evidence_summary(ctx)
        chain_summary = self._build_chain_summary(ctx)
        confidence_summary = self._build_confidence_summary(ctx)
        legal_refs = self._build_legal_refs(ctx)

        # 提取证据链关键结论
        chain_status = "unknown"
        chain_conf = 0.0
        for ch in ctx.evidence_chains:
            chain_status = ch.get("status", "unknown")
            chain_conf = ch.get("confidence", 0.0)
            break

        status_instruction = {
            "pass": "【重要】证据链状态为 PASS(通过)，报告结论应为证据确实充分、可以认定。",
            "review": "【重要】证据链状态为 REVIEW(需复核)，报告应指出证据基本充分但存在需核实之处，建议补强。",
            "reject": "【重要】证据链状态为 REJECT(驳回)，报告必须明确指出证据严重不足、无法认定、建议补充侦查。严禁出现'证据确实充分'等肯定性结论。",
        }.get(chain_status, "")

        prompt = f"""请根据以下信息生成证据链审查报告：

═══════════════════════════════════════
【案件背景】
{ctx.case_context or ctx.query or "（待补充）"}

【评估问题】
{ctx.query or "证据链是否完整？"}

【证据汇总】
{evidence_summary}

【证据链分析结果】
{chain_summary}

{status_instruction}

【法条引用】
{legal_refs}

【置信度评估】
{confidence_summary}

═══════════════════════════════════════

请生成正式的证据链审查报告。报告中必须自然地提及上述证据类型、法条和置信度评估结果。
证据链分析结论和置信度必须原样保留，不得修改或弱化。"""

        return await self.llm.generate(
            prompt=prompt,
            system=LLM_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.3,
        )

    # ═══════════════════════════════════════════════
    # 上下文构建（给 LLM 输送结构化数据）
    # ═══════════════════════════════════════════════

    @staticmethod
    def _build_evidence_summary(ctx: AgentContext) -> str:
        lines = []
        for ch in ctx.evidence_chains:
            for ev in ch.get("supporting_evidence", []):
                chunk_id = ev.get("chunk_id", "")
                if chunk_id.startswith("parsed-"):
                    continue  # 跳过关键词提取的假条目
                lines.append(
                    f"  - [{ev.get('type', '证据')}] "
                    f"{ev.get('content', '')[:100]} "
                    f"(来源: {chunk_id[:20]})"
                )
        if not lines:
            # 没有真实证据时，直接从 case_context 提取
            lines.append(f"  案件描述: {(ctx.case_context or '')[:300]}")
        return "\n".join(lines) if lines else "（待补充证据材料）"

    @staticmethod
    def _build_chain_summary(ctx: AgentContext) -> str:
        lines = []
        for ch in ctx.evidence_chains:
            status_label = {
                "pass": "✓ 通过",
                "review": "⚠ 需复核",
                "reject": "✗ 驳回",
            }.get(ch.get("status", ""), "未知")
            lines.append(f"  证据链 {ch.get('chain_id', '?')}: {status_label}")
            lines.append(f"    待证事实: {ch.get('fact_to_prove', '')}")
            lines.append(f"    法律依据: {ch.get('legal_basis', '')}")
            lines.append(f"    置信度: {ch.get('confidence', 0):.2f}")
            missing = ch.get("missing_evidence", [])
            if missing:
                lines.append(f"    缺失证据: {', '.join(missing)}")
            reasoning = ch.get("llm_reasoning", "")
            if reasoning:
                lines.append(f"    分析: {reasoning[:200]}")
        return "\n".join(lines) if lines else "（无证据链分析）"

    @staticmethod
    def _build_confidence_summary(ctx: AgentContext) -> str:
        dims = ctx.confidence_dimensions
        if not dims:
            return f"综合置信度: {ctx.final_confidence:.2f}（{ctx.threshold_result}）"
        lines = [f"综合置信度: {ctx.final_confidence:.2f}（{ctx.threshold_result}）", ""]
        for d in dims:
            lines.append(f"  - {d['label']}: {d['value']:.2f} (权重: {d['weight']})")
        return "\n".join(lines)

    @staticmethod
    def _build_legal_refs(ctx: AgentContext) -> str:
        refs = set()
        for ch in ctx.evidence_chains:
            if ch.get("legal_basis"):
                refs.add(ch["legal_basis"])
        # 从检索法条
        for s in ctx.retrieved_statutes[:3]:
            refs.add(s.get("law_name", "") or s.get("content", "")[:30])
        return "\n".join(f"  - {r}" for r in refs) if refs else "（无法条引用）"

    # ═══════════════════════════════════════════════
    # 模板 fallback
    # ═══════════════════════════════════════════════

    @staticmethod
    def _generate_template(ctx: AgentContext) -> str:
        """模板报告（LLM 不可用时的 fallback）。"""
        materials_summary = (
            f"本案解析材料 {len(ctx.material_ids)} 件。\n"
            f"抽取司法要素 {len(ctx.extracted_elements)} 项。\n"
            f"向量检索命中相关法条 {len(ctx.retrieved_statutes)} 条、"
            f"案件证据片段 {len(ctx.retrieved_chunks)} 条。\n"
            f"构建图谱节点 {len(ctx.graph_nodes)} 个、关系边 {len(ctx.graph_edges)} 条。"
        )

        chains_content = []
        for ch in ctx.evidence_chains:
            support_list = "\n".join(
                f"  - [{ev['type']}] {ev['content'][:80]}"
                f"（来源: {ev.get('chunk_id', '?')[:20]}）"
                for ev in ch.get("supporting_evidence", [])
            )
            missing = (
                "、".join(ch.get("missing_evidence", []))
                if ch.get("missing_evidence")
                else "无"
            )
            status_label = {
                "pass": "✓ 通过",
                "review": "⚠ 需复核",
                "reject": "✗ 驳回",
            }.get(ch.get("status", ""), ch.get("status", ""))

            chains_content.append(
                f"### {ch['chain_id']} {status_label}\n\n"
                f"- 待证事实：{ch['fact_to_prove']}\n"
                f"- 法律依据：{ch['legal_basis']}\n"
                f"- 置信度：{ch['confidence']:.2f}\n"
                f"- 支撑证据：\n{support_list}\n"
                f"- 缺失证据：{missing}"
            )

        if ctx.conflicts:
            conflicts_text = "\n".join(
                f"- [{c['risk_level']}风险] {c['type']}：{c['claim_a']} ↔ {c['claim_b']}"
                f" → {c['resolution']}"
                for c in ctx.conflicts
            )
        else:
            conflicts_text = "未发现明显证据冲突。"

        dims_text = "\n".join(
            f"| {d['label']} | {d['value']:.2f} | ×{d['weight']} |"
            for d in ctx.confidence_dimensions
        )
        threshold_label = {
            "pass": "通过（≥0.85）",
            "review": "需复核（0.70-0.85）",
            "uncertain": "存疑（0.50-0.70）",
            "reject": "驳回（<0.50）",
        }.get(ctx.threshold_result, ctx.threshold_result)

        confidence_text = (
            f"综合置信度：**{ctx.final_confidence:.2f}**（{threshold_label}）\n\n"
            f"| 维度 | 得分 | 权重 |\n|------|------|------|\n{dims_text}"
        )

        all_missing = []
        for ch in ctx.evidence_chains:
            for m in ch.get("missing_evidence", []):
                if m not in all_missing:
                    all_missing.append(m)
        supplementation = (
            "\n".join(f"{i}. {m}" for i, m in enumerate(all_missing, 1))
            if all_missing
            else "当前证据链完整，无需补充侦查。"
        )

        sources = []
        for s in ctx.retrieved_statutes[:5]:
            sources.append(
                f"| {s.get('chunk_id', '')[:20]} | 法条 | "
                f"{s.get('law_name', '')} ({s.get('effective_date', '')[:10]}) |"
                f" {s.get('distance', 0):.3f} |"
            )
        for c in ctx.retrieved_chunks[:5]:
            sources.append(
                f"| {c.get('chunk_id', '')[:20]} | {c.get('evidence_type', '证据')} | "
                f"{c.get('content', '')[:60]} | {c.get('distance', 0):.3f} |"
            )
        source_table = (
            "| ID | 类型 | 内容/来源 | 距离 |\n"
            "|----|------|-----------|------|\n"
            + "\n".join(sources)
        )

        sections = [
            ("一、案件材料处理概况", materials_summary),
            ("二、核心证据链分析", "\n\n".join(chains_content)),
            ("三、对立证据与风险识别", conflicts_text),
            ("四、置信度审查说明", confidence_text),
            ("五、补证与复核建议", supplementation),
            ("六、主要溯源清单", source_table),
        ]

        return "\n".join(
            f"## {heading}\n\n{content}\n" for heading, content in sections
        )
