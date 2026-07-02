"""报告生成 Agent — architecture.md §5.8, §7

从流水线上游的所有 Agent 产出中生成可溯源报告。
LLM 模式下使用 DeepSeek 生成自然语言报告，模板为 fallback。
"""

import json
import re as _re

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext

LLM_SYSTEM_PROMPT = """你是中国刑事证据审查专家助理，负责撰写证据链审查报告。

核心规则（不可违反）：
1. 严格基于提供的证据材料撰写，不得编造事实
2. 每个结论必须附带证据来源引用
3. 引用相关法条（刑法、刑事诉讼法）
4. 低置信度结论必须标注"待核实"
5. 证据链状态为 驳回 时，报告必须明确指出"证据不足"，严禁使用"证据确实充分"

报告结构：
## 一、案件基本情况
## 二、案件材料处理概况
## 三、核心证据链分析
## 四、对立证据与风险识别
## 五、置信度审查说明
## 六、补证与复核建议
## 七、主要溯源清单

请直接输出报告正文，不要输出 JSON 或其他格式。"""


# ══════════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════════


def _readable_source(chunk_id: str) -> str:
    """将 chunk_id 转为可读的来源引用。

    >>> _readable_source("parsed-鉴定意见")
    '📋 关键词匹配 · 鉴定意见'
    >>> _readable_source("478e3b4a-3e45-...")
    '📄 材料 478e3b4a'
    >>> _readable_source("CASE-001:MAT-abc:chunk_0002")
    '📄 CASE-001 第0002段'
    """
    if not chunk_id:
        return "未知来源"

    # 关键词解析的假条目
    if chunk_id.startswith("parsed-"):
        label = chunk_id.replace("parsed-", "")
        return f"📋 关键词匹配 · {label}"

    # UUID 格式 → 截短
    if _re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-', chunk_id):
        return f"📄 材料 {chunk_id[:8]}"

    # 带冒号的结构化 ID
    if ':' in chunk_id:
        parts = chunk_id.split(':')
        # CASE:MAT:chunk_NNNN
        if len(parts) >= 3:
            case = parts[0][:12]
            idx = parts[-1].replace("chunk_", "段")
            return f"📄 {case} {idx}"
        return f"📄 {parts[0][:16]}"

    return f"📄 {chunk_id[:20]}"


def _extract_evidence_from_context(text: str, keywords: list[str], context_chars: int = 80) -> list[str]:
    """从文本中提取包含指定关键词的句子片段。

    不再取全文前 80 字——而是定位关键词所在句子，做到各证据类型内容不同。
    """
    if not text:
        return []
    results = []
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0:
            start = max(0, idx - 20)
            end = min(len(text), idx + context_chars)
            snippet = text[start:end].strip()
            # 截断到最近的句号
            dot = snippet.rfind("。")
            if dot > len(snippet) // 2:
                snippet = snippet[:dot + 1]
            results.append(snippet)
    return results


def _extract_key_sentence(text: str, keyword: str, radius: int = 60) -> str:
    """提取关键词周围的一句话片段。"""
    idx = text.find(keyword)
    if idx < 0:
        return text[:radius * 2] + ("..." if len(text) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(text), idx + radius)
    snippet = text[start:end].strip()
    # 对齐到句号边界
    if start > 0:
        first_dot = snippet.find("。")
        if 0 < first_dot < radius:
            snippet = snippet[first_dot + 1:]
    last_dot = snippet.rfind("。")
    if last_dot > len(snippet) * 0.6:
        snippet = snippet[:last_dot + 1]
    return snippet.strip()


def _chunk_display_name(chunk: dict) -> str:
    """返回 chunk 的人类可读名称。"""
    etype = chunk.get("evidence_type", "")
    if etype:
        return etype
    cid = chunk.get("chunk_id", "")
    if cid.startswith("parsed-"):
        return cid.replace("parsed-", "")
    return "证据片段"


def _chunk_location(chunk: dict) -> str:
    """提取 chunk 的可追溯定位信息。"""
    sp = chunk.get("source_pointer", {}) or {}
    if isinstance(sp, str):
        try:
            sp = json.loads(sp)
        except Exception:
            sp = {}

    material = sp.get("material_id", "") or chunk.get("material_id", "") or chunk.get("case_id", "")
    page = sp.get("page", "") or sp.get("page_number", "")
    para = sp.get("paragraph", "")

    parts = []
    if material:
        if len(str(material)) > 20:
            parts.append(f"材料 {str(material)[:8]}…")
        else:
            parts.append(str(material))
    if page:
        parts.append(f"第{page}页")
    if para is not None and para != "":
        parts.append(f"第{para}段")

    if parts:
        return "，".join(parts)
    return _readable_source(chunk.get("chunk_id", ""))


# ══════════════════════════════════════════════════════════════════════


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
        ctx.report_sections = []
        return ctx

    # ═══════════════════════════════════════════════════════════════
    # LLM 报告
    # ═══════════════════════════════════════════════════════════════

    async def _generate_with_llm(self, ctx: AgentContext) -> str:
        evidence_summary = self._build_evidence_summary(ctx)
        chain_summary = self._build_chain_summary(ctx)
        confidence_summary = self._build_confidence_summary(ctx)
        legal_refs = self._build_legal_refs(ctx)

        chain_status = "unknown"
        for ch in ctx.evidence_chains:
            chain_status = ch.get("status", "unknown")
            break

        status_instruction = {
            "pass": "【重要】证据链状态为 PASS(通过)，结论应为证据确实充分。",
            "review": "【重要】证据链状态为 REVIEW(需复核)，应指出需核实之处，建议补强。",
            "reject": "【重要】证据链状态为 REJECT(驳回)，必须指出证据不足、无法认定。严禁出现'证据确实充分'。",
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

请生成正式的证据链审查报告。证据链分析结论和置信度必须原样保留，不得修改。"""

        return await self.llm.generate(
            prompt=prompt,
            system=LLM_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.3,
        )

    # ═══════════════════════════════════════════════════════════════
    # LLM 上下文构建
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _build_evidence_summary(ctx: AgentContext) -> str:
        lines = []
        for ch in ctx.evidence_chains:
            for ev in ch.get("supporting_evidence", []):
                chunk_id = ev.get("chunk_id", "")
                if chunk_id.startswith("parsed-"):
                    continue
                lines.append(
                    f"  - [{ev.get('type', '证据')}] "
                    f"{ev.get('content', '')[:100]} "
                    f"(来源: {chunk_id[:20]})"
                )
        if not lines:
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
        for s in ctx.retrieved_statutes[:3]:
            refs.add(s.get("law_name", "") or s.get("content", "")[:30])
        return "\n".join(f"  - {r}" for r in refs) if refs else "（无法条引用）"

    # ═══════════════════════════════════════════════════════════════
    # 模板 fallback（重点改进：清晰排版）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _generate_template(ctx: AgentContext) -> str:
        """生成清晰可读的模板报告。"""
        sections = [
            _section_one(ctx),
            _section_two(ctx),
            _section_three(ctx),
            _section_four(ctx),
            _section_five(ctx),
            _section_six(ctx),
            _section_seven(ctx),
        ]
        # 双换行分隔各节
        return "\n\n".join(sections)


# ══════════════════════════════════════════════════════════════════════
# 各节渲染函数
# ══════════════════════════════════════════════════════════════════════


def _section_one(ctx: AgentContext) -> str:
    """一、案件基本情况。"""
    case_text = ctx.case_context or ctx.query or "（待补充）"

    lines = [
        "## 一、案件基本情况\n",
        f"**案由**：{ctx.query or '（待补充）'}",
    ]

    if ctx.case_name:
        lines.append(f"**案件名称**：{ctx.case_name}")
    if ctx.case_context:
        lines.append(f"\n**案件事实**：\n\n{ctx.case_context.strip()[:500]}")

    # 要素列表
    if ctx.extracted_elements:
        high_conf = [e for e in ctx.extracted_elements if e.get("confidence", 0) >= 0.7]
        if high_conf:
            lines.append(f"\n**关键要素**（已抽取 {len(high_conf)} 项）：\n")
            for e in high_conf[:10]:
                lines.append(
                    f"- {e.get('category', '?')}：{e.get('value', '?')}"
                    f"（置信度 {e.get('confidence', 0):.0%}）"
                )

    return "\n".join(lines)


def _section_two(ctx: AgentContext) -> str:
    """二、案件材料处理概况。"""
    lines = [
        "## 二、案件材料处理概况\n",
        f"- 卷宗材料：{len(ctx.material_ids)} 件",
        f"- 司法要素：{len(ctx.extracted_elements)} 项",
        f"- 检索法条：{len(ctx.retrieved_statutes)} 条",
        f"- 证据片段：{len(ctx.retrieved_chunks)} 条",
        f"- 图谱节点：{len(ctx.graph_nodes)} 个 ｜ 关系边：{len(ctx.graph_edges)} 条",
    ]
    return "\n".join(lines)


def _section_three(ctx: AgentContext) -> str:
    """三、核心证据链分析。"""
    lines = ["## 三、核心证据链分析\n"]

    if not ctx.evidence_chains:
        lines.append("（暂无证据链分析结果）")
        return "\n".join(lines)

    for ch_idx, ch in enumerate(ctx.evidence_chains):
        status = ch.get("status", "")
        status_label = {
            "pass": "✅ 通过",
            "review": "⚠️ 需复核",
            "reject": "❌ 驳回",
        }.get(status, status)

        confidence = ch.get("confidence", 0)

        lines.append(
            f"### 证据链 {ch_idx + 1}：{status_label}"
            f"（置信度 {confidence:.0%}）\n"
        )
        lines.append(f"**待证事实**：{ch.get('fact_to_prove', '待补充')}")
        lines.append(f"**法律依据**：{ch.get('legal_basis', '相关法律条文')}")

        # 支撑证据 —— 每项独立段落，空行分隔（兼容前端简易 Markdown 渲染器）
        support_ev = ch.get("supporting_evidence", [])
        if support_ev:
            # 去重：相同类型只保留一个
            seen_types = set()
            unique_ev = []
            for ev in support_ev:
                etype = ev.get("type", "") or _chunk_display_name(ev)
                if etype not in seen_types:
                    seen_types.add(etype)
                    unique_ev.append(ev)

            lines.append(f"\n**支撑证据**（{len(unique_ev)} 类）：\n")
            for ev in unique_ev:
                etype = ev.get("type", "") or _chunk_display_name(ev)
                content = ev.get("content", "")
                loc = _chunk_location(ev)

                # 限制内容长度
                display_content = content[:200]
                if len(content) > 200:
                    display_content += "…"

                # 用空行分隔的独立段落，确保前端逐项分行渲染
                lines.append(f"**{etype}**")
                lines.append(f"{display_content}")
                lines.append(f"> 来源：{loc}")
                lines.append("")  # 空行分隔
            lines.append("\n（无具体证据项）\n")

        # 缺失证据
        missing = ch.get("missing_evidence", [])
        if missing and missing != ["无"]:
            lines.append(f"**缺失证据**：{'、'.join(m for m in missing if m)}")

        # 分析说明
        reasoning = ch.get("llm_reasoning", "")
        if reasoning:
            lines.append(f"\n**分析说明**：{reasoning[:300]}")

        lines.append("")  # 链间分隔

    return "\n".join(lines)


def _section_four(ctx: AgentContext) -> str:
    """四、对立证据与风险识别。"""
    lines = ["## 四、对立证据与风险识别\n"]

    if not ctx.conflicts:
        lines.append("经审查，未发现明显证据冲突或对立。")
        return "\n".join(lines)

    for c in ctx.conflicts:
        risk = c.get("risk_level", "?")
        risk_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(risk, "⚪")
        lines.append(f"\n### {risk_icon} {risk}风险：{c.get('type', '未知冲突')}\n")
        lines.append(f"- 甲方：{c.get('claim_a', '')}")
        lines.append(f"- 乙方：{c.get('claim_b', '')}")
        lines.append(f"- 建议：{c.get('resolution', '')}")

    return "\n".join(lines)


def _section_five(ctx: AgentContext) -> str:
    """五、置信度审查说明。

    使用对齐的纯文本格式替代 Markdown 表格，避免终端渲染问题。
    """
    lines = ["## 五、置信度审查说明\n"]

    threshold_label = {
        "pass": "通过（≥ 0.85）",
        "review": "需复核（0.70 ~ 0.85）",
        "uncertain": "存疑（0.50 ~ 0.70）",
        "reject": "驳回（< 0.50）",
    }.get(ctx.threshold_result, ctx.threshold_result or "—")

    lines.append(f"**综合置信度**：{ctx.final_confidence:.2f}  →  {threshold_label}")
    lines.append("")

    dims = ctx.confidence_dimensions
    if dims:
        # 表格头
        lines.append("```")
        lines.append(f"{'维度':　<12} {'得分':>6}  {'权重':>6}  {'加权':>6}")
        lines.append(f"{'─' * 12} {'─' * 6}  {'─' * 6}  {'─' * 6}")
        for d in dims:
            label = d.get("label", "?")
            value = d.get("value", 0)
            weight = d.get("weight", 0)
            weighted = value * weight
            lines.append(f"{label:　<12} {value:6.2f}  {weight:6.2f}  {weighted:6.2f}")
        lines.append("```")
    else:
        lines.append("（暂无维度评分数据）")

    return "\n".join(lines)


def _section_six(ctx: AgentContext) -> str:
    """六、补证与复核建议。"""
    lines = ["## 六、补证与复核建议\n"]

    # 收集所有缺失证据
    all_missing = []
    for ch in ctx.evidence_chains:
        for m in ch.get("missing_evidence", []):
            if m and m not in all_missing and m != "无":
                all_missing.append(m)

    # 判断是否需要补充
    has_reject = any(ch.get("status") == "reject" for ch in ctx.evidence_chains)
    has_review = any(ch.get("status") == "review" for ch in ctx.evidence_chains)

    if has_reject:
        lines.append("⚠️ 证据链存在严重缺陷，建议采取以下措施：\n")
        lines.append("1. 补充侦查，调取缺失的关键证据")
        lines.append("2. 核实现有证据的合法性和真实性")
        lines.append("3. 重新审查案件事实认定依据")
    elif all_missing:
        lines.append("建议补充以下证据：\n")
        for i, m in enumerate(all_missing, 1):
            lines.append(f"{i}. {m}")
    elif has_review:
        lines.append("证据基本充分，建议对存疑项进行复核。")
    else:
        lines.append("当前证据链完整，无需补充侦查。")

    return "\n".join(lines)


def _section_seven(ctx: AgentContext) -> str:
    """七、主要溯源清单。

    使用分组列表替代 Markdown 表格，清晰可读。
    """
    lines = ["## 七、主要溯源清单\n"]

    # ── 法条来源 ──
    statutes = ctx.retrieved_statutes[:5]
    if statutes:
        lines.append("### 引用法条\n")
        for i, s in enumerate(statutes, 1):
            law_name = s.get("law_name", "") or s.get("name", "") or "法律条文"
            content = s.get("content", "") or s.get("content_preview", "") or ""
            # 提取条文号
            article = _re.search(
                r'(第[一二三四五六七八九十百千\d]+条(?:之[一二三四五\d]+)?)',
                content
            )
            article_str = f" {article.group(1)}" if article else ""
            # 清洗 content
            core = _re.sub(r'^#+\s*', '', content).replace('\n', ' ').strip()[:100]
            date = s.get("effective_date", "")[:10]

            lines.append(f"{i}. **{law_name}**{article_str}")
            if date:
                lines.append(f"   生效日期：{date}")
            lines.append(f"   {core}")
            lines.append("")

    # ── 证据来源 ──
    chunks = ctx.retrieved_chunks[:8]
    if chunks:
        # 去重
        seen = set()
        unique_chunks = []
        for c in chunks:
            key = (c.get("content", "") or "")[:60]
            if key not in seen:
                seen.add(key)
                unique_chunks.append(c)

        lines.append("### 证据材料\n")
        for i, c in enumerate(unique_chunks, 1):
            etype = c.get("evidence_type", "") or "证据"
            content = (c.get("content", "") or c.get("content_preview", "") or "")
            content = content.replace('\n', ' ').strip()[:120]
            loc = _chunk_location(c)

            lines.append(f"{i}. **{etype}**")
            lines.append(f"   定位：{loc}")
            lines.append(f"   内容：{content}")
            lines.append("")

    # ── 补充：从 evidence_chains 抓取模板中没有的 ──
    seen_texts = set()
    for c in chunks:
        seen_texts.add((c.get("content", "") or "")[:60])
    extra_sources = []
    for ch in ctx.evidence_chains:
        for ev in ch.get("supporting_evidence", []):
            content = (ev.get("content", "") or "").replace('\n', ' ').strip()[:120]
            if content[:60] not in seen_texts:
                seen_texts.add(content[:60])
                extra_sources.append(ev)
    if extra_sources:
        lines.append("### 补充来源\n")
        for i, ev in enumerate(extra_sources, 1):
            etype = ev.get("type", "") or _chunk_display_name(ev)
            content = (ev.get("content", "") or "").replace('\n', ' ').strip()[:120]
            loc = _readable_source(ev.get("chunk_id", ""))
            lines.append(f"{i}. **{etype}** ｜ {loc}")
            lines.append(f"   {content}")
            lines.append("")

    if not statutes and not chunks and not extra_sources:
        lines.append(
            "暂无检索结果，无法建立溯源清单。\n\n"
            "> 💡 上传卷宗材料或选择有证据片段的案件进行分析后，"
            "溯源清单将自动生成。"
        )

    return "\n".join(lines)
