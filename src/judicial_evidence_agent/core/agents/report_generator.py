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

格式要求（重要）：
- 案件事实、证据清单等内容必须用列表/分点呈现，不可用长段落堆砌
- 每个证据项独占一行，以 "- " 开头
- 要素抽取结果用表格或分点展示
- 大段文字超过 3 行必须拆分为小段落或列表

报告结构：
## 一、案件基本情况（事实描述用分点列表）
## 二、案件材料处理概况
## 三、核心证据链分析
## 四、对立证据与风险识别
## 五、置信度审查说明
## 六、补证与复核建议
## 七、主要溯源清单

请直接输出报告正文，不要输出 JSON 或其他格式。"""


def _readable_source(chunk_id: str) -> str:
    """将 chunk_id 转为可读的来源引用。"""
    import re
    if not chunk_id:
        return "未知来源"
    # UUID 格式 → 截短
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-', chunk_id):
        return f"材料 {chunk_id[:8]}..."
    # 带前缀的 → 保留可读部分
    if ':' in chunk_id:
        prefix, rest = chunk_id.split(':', 1)
        return f"{prefix} · {rest[:12]}"
    return chunk_id[:24]


def _split_to_bullets(text: str, min_len: int = 8) -> list[str]:
    """将长文本按中文标点拆分为分点列表。"""
    import re
    # 按句号、分号、换行拆分
    parts = re.split(r"[。；\n]+", text)
    # 清理空白，过滤过短片段
    result = []
    for p in parts:
        p = p.strip().rstrip("，,、")
        if len(p) >= min_len:
            result.append(p)
    # 如果没有够长的片段，原样返回
    return result if result else [text.strip()[:200]]


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
        """模板报告（规则引擎 / LLM 不可用时的 fallback）。"""
        # ── 一、案件基本情况 ──
        case_text = ctx.case_context or ctx.query or "（待补充）"
        # 将长文本按句号/分号拆为分点
        facts_list = _split_to_bullets(case_text)

        case_info_lines = [
            f"- **案由**: {ctx.query or '（待补充）'}",
            "- **事实描述**:",
        ]
        for fact in facts_list:
            case_info_lines.append(f"  - {fact}")
        # 要素列表分点
        if ctx.extracted_elements:
            case_info_lines.append(f"\n**已抽取要素** ({len(ctx.extracted_elements)} 项):")
            for e in ctx.extracted_elements[:10]:
                conf = e.get("confidence", 0)
                icon = "✓" if conf >= 0.8 else "⚠" if conf >= 0.6 else "✗"
                case_info_lines.append(f"  - {icon} {e.get('category', '?')}: {e.get('value', '?')} （置信度 {conf:.0%}）")
        case_info = "\n".join(case_info_lines)

        # ── 案件材料概况 ──
        materials_summary = (
            f"- 卷宗材料: {len(ctx.material_ids)} 件\n"
            f"- 司法要素: {len(ctx.extracted_elements)} 项\n"
            f"- 检索法条: {len(ctx.retrieved_statutes)} 条\n"
            f"- 证据片段: {len(ctx.retrieved_chunks)} 条\n"
            f"- 图谱节点: {len(ctx.graph_nodes)} 个 / 关系边: {len(ctx.graph_edges)} 条"
        )

        # ── 核心证据链 ──
        chains_content = []
        for ch in ctx.evidence_chains:
            status_label = {
                "pass": "✓ 通过",
                "review": "⚠ 需复核",
                "reject": "✗ 驳回",
            }.get(ch.get("status", ""), ch.get("status", ""))

            support_ev = ch.get("supporting_evidence", [])
            if support_ev:
                support_parts = []
                for i, ev in enumerate(support_ev[:8]):
                    etype = ev.get('type', '证据')
                    content = ev.get('content', '')[:150]
                    src = ev.get('chunk_id', '?')
                    # 尽量展示可读来源而非原始 UUID
                    src_display = _readable_source(src)
                    support_parts.append(
                        f"  {i+1}. **[{etype}]** {content}"
                        f"\n     > 📎 {src_display}"
                    )
                support_list = "\n".join(support_parts)
            else:
                support_list = "  （无具体证据项）"

            missing = ch.get("missing_evidence", [])
            missing_text = "\n".join(f"  - {m}" for m in missing) if missing else "  无"

            reasoning = ch.get("llm_reasoning", "")
            reasoning_block = f"\n- **分析说明**: {reasoning[:300]}" if reasoning else ""

            chains_content.append(
                f"### {status_label} — {ch.get('fact_to_prove', '待证事实')}\n\n"
                f"- **法律依据**: {ch.get('legal_basis', '刑法相关条文')}\n"
                f"- **综合置信度**: **{ch.get('confidence', 0):.0%}**\n"
                f"- **支撑证据**:\n{support_list}\n"
                f"- **缺失证据**:\n{missing_text}"
                f"{reasoning_block}"
            )

        # ── 对立证据与风险 ──
        if ctx.conflicts:
            conflicts_text = "\n".join(
                f"- **[{c.get('risk_level','?')}风险]** {c.get('type','')}\n"
                f"  - 甲方: {c.get('claim_a','')}\n"
                f"  - 乙方: {c.get('claim_b','')}\n"
                f"  - 建议: {c.get('resolution','')}"
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
        # ── 法条来源：提取条文编号 + 关键内容 ──
        import re as _re
        for s in ctx.retrieved_statutes[:5]:
            law_name = s.get('law_name', '') or '法律条文'
            content = (s.get('content', '') or s.get('content_preview', '') or '')
            # 提取条文号：第X条、第X条之Y
            article = _re.search(r'(第[一二三四五六七八九十百千\d]+条(?:之[一二三四五\d]+)?)', content)
            article_str = article.group(1) if article else ''
            # 取法条核心内容（去掉标题标记，限50字分行）
            core = _re.sub(r'^#+\s*', '', content)
            core = core.replace('\n', ' ').strip()[:50]
            sources.append(
                f"| {law_name[:20]} | {article_str} | {core}... |"
            )

        # ── 证据来源：提取可追溯的定位信息 ──
        for c in ctx.retrieved_chunks[:8]:
            etype = c.get('evidence_type', '证据')[:8]
            content = (c.get('content', '') or c.get('content_preview', '') or '')
            content = content.replace('\n', ' ').strip()[:50]
            # 尝试从 source_pointer 或 meta 提取真实定位
            sp = c.get('source_pointer', {}) or {}
            if isinstance(sp, str):
                try: import json; sp = json.loads(sp)
                except: sp = {}
            material = sp.get('material_id', '') or c.get('material_id', '') or c.get('case_id', '')
            page = sp.get('page', '') or sp.get('page_number', '')
            para = sp.get('paragraph', '') or sp.get('line_number', '')
            loc = f"卷{str(material)[:12]}" if material else ''
            if page: loc += f" 第{page}页"
            if para: loc += f" 第{para}段"
            if not loc: loc = f"材料 ({str(c.get('chunk_id',''))[:8]}...)"
            sources.append(
                f"| {etype} | {loc} | {content}... |"
            )

        # ── 从证据链补充 ──
        seen_contents = set()
        for s in sources:
            seen_contents.add(s[50:150])  # 内容片段去重
        for ch in ctx.evidence_chains:
            for ev in ch.get("supporting_evidence", []):
                content = (ev.get('content', '') or '').replace('\n', ' ').strip()[:50]
                if content[:40] in seen_contents:
                    continue
                seen_contents.add(content[:40])
                etype = ev.get('type', '证据')[:8]
                cid = ev.get('chunk_id', '')
                src = _readable_source(cid)
                sources.append(
                    f"| {etype} | {src} | {content}... |"
                )

        if sources:
            source_table = (
                "| 法条/证据 | 定位 | 内容摘要 |\n"
                "|-----------|------|----------|\n"
                + "\n".join(sources[:15])
            )
        else:
            source_table = (
                "暂无检索结果，无法建立溯源清单。\n\n"
                "> 💡 溯源清单在完成检索后自动生成，包含每项证据的可追溯定位信息。\n"
                "> 建议：上传卷宗材料或选择有证据片段的案件进行分析。"
            )

        sections = [
            ("一、案件基本情况", case_info),
            ("二、案件材料处理概况", materials_summary),
            ("三、核心证据链分析", "\n\n".join(chains_content)),
            ("四、对立证据与风险识别", conflicts_text),
            ("五、置信度审查说明", confidence_text),
            ("六、补证与复核建议", supplementation),
            ("七、主要溯源清单", source_table),
        ]

        return "\n".join(
            f"## {heading}\n\n{content}\n" for heading, content in sections
        )
