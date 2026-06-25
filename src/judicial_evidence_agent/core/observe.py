"""规则优先 Observe — 在每个 LLM 调用前判断：规则能拍板就不调 LLM。

参考 HouseInsight-Agent 的 "计划→执行→观察→重规划" 模式，
将 Observe 层嵌入现有流水线，LLM 只在规则无法确定时才介入。

每条规则返回 (should_use_llm: bool, reason: str, fallback_result: dict | None)
"""

from __future__ import annotations

from typing import Optional

from judicial_evidence_agent.core.agents.base import AgentContext


# ══════════════════════════════════════════════════════════════════════
# 1. 要素抽取 Observe
# ══════════════════════════════════════════════════════════════════════

def observe_element_extraction(ctx: AgentContext) -> tuple[bool, str, Optional[list[dict]]]:
    """判断要素抽取是否需要 LLM。

    规则:
    - 案情 < 50 字 → 规则抽取即可
    - 案情 50~200 字 + 无争议关键词 → 规则抽取
    - 案情 > 200 字 或 含争议关键词 → 需要 LLM
    """
    text = f"{ctx.case_context} {ctx.query}"
    text_len = len(text)

    dispute_keywords = ["刑讯逼供", "非法证据", "正当防卫", "翻供", "窜供",
                        "共犯", "主从犯", "立功", "自首", "未遂", "既遂"]
    has_dispute = any(kw in text for kw in dispute_keywords)

    if text_len < 50:
        return False, f"案情简短({text_len}字)，规则抽取足够", None
    if text_len < 200 and not has_dispute:
        return False, f"案情中等({text_len}字)且无争议焦点，规则抽取", None
    return True, f"案情较长({text_len}字)或含争议焦点，需LLM语义分析", None


# ══════════════════════════════════════════════════════════════════════
# 2. 知识图谱 Observe
# ══════════════════════════════════════════════════════════════════════

def observe_graph_building(ctx: AgentContext) -> tuple[bool, str, Optional[dict]]:
    """判断图谱构建是否需要 LLM（激进策略 — 只有严重不足才调 LLM）。"""
    elements = ctx.extracted_elements
    categories = {e.get("category", "") for e in elements}

    has_dispute = "争议焦点" in categories
    text_len = len(ctx.case_context or "")

    # 要素 >= 3 → 规则绝对够
    if len(elements) >= 3:
        return False, f"要素充足({len(elements)}项/{len(categories)}类)，规则构建", None

    # 要素虽少但案情简单
    if len(elements) < 3 and text_len < 80:
        return False, f"简单案件(text_len={text_len})，规则构建", None

    # 只有争议焦点且无其他要素 → 才需要 LLM
    if has_dispute and len(elements) < 2:
        return True, "仅有争议焦点，需要LLM推断完整关系", None

    return False, f"要素{len(elements)}项，规则构建", None


# ══════════════════════════════════════════════════════════════════════
# 3. 证据链分析 Observe
# ══════════════════════════════════════════════════════════════════════

def observe_evidence_chain(ctx: AgentContext) -> tuple[bool, str, Optional[dict]]:
    """判断证据链分析是否需要 LLM。

    这是最关键的 Observe 点——证据链分析是核心判断，
    规则明确时跳过 LLM 能省最多时间。

    规则:
    - 检索chunk数 >= 5 且 证据类型 >= 3 → 证据充足，规则分析
    - 检索chunk数 >= 3 且 含法条 → 规则分析
    - 检索chunk数 = 0 → 证据不足，直接 reject（不用调 LLM）
    - 检索chunk数 1~2 且 无语义复杂项 → 规则分析
    - 含复杂争议（如非法证据排除）→ 需要 LLM
    """
    chunk_count = len(ctx.retrieved_chunks)
    statute_count = len(ctx.retrieved_statutes)

    # 证据类型多样性
    evidence_types = set()
    for c in ctx.retrieved_chunks:
        etype = c.get("evidence_type", "")
        if etype:
            evidence_types.add(etype)

    # 从要素中统计证据类型
    for e in ctx.extracted_elements:
        if e.get("category") == "证据名称":
            evidence_types.add(e.get("value", ""))

    type_count = len(evidence_types)

    # 完全没检索到 → 直接 reject
    if chunk_count == 0 and statute_count == 0:
        return False, "无检索结果，直接驳回（无需LLM）", {
            "chain_status": "reject",
            "evidence_types": list(evidence_types) if evidence_types else ["无"],
            "missing_evidence": ["无任何检索到的证据或法条，建议补充卷宗材料"],
            "confidence": 0.10,
            "reasoning": "规则Observe判定：检索命中数为0，证据链不成立",
        }

    # 证据充足且类型丰富 → 规则直接通过（确定）
    if chunk_count >= 5 and type_count >= 3:
        return False, f"证据充足({chunk_count}条/{type_count}类)，规则通过", {
            "chain_status": "pass",
            "evidence_types": list(evidence_types),
            "missing_evidence": [],
            "confidence": min(0.85 + type_count * 0.02, 0.95),
            "reasoning": f"规则判定：检索到{chunk_count}条证据/{type_count}类，证据链完整",
        }

    # 完全没检索到 → 直接驳回（确定）
    if chunk_count == 0 and statute_count == 0:
        return False, "无检索结果，直接驳回", {
            "chain_status": "reject",
            "evidence_types": list(evidence_types) if evidence_types else ["无"],
            "missing_evidence": ["无任何检索到的证据或法条，建议补充卷宗材料"],
            "confidence": 0.10,
            "reasoning": "规则判定：检索命中数为0，证据链不成立",
        }

    # 其他所有情况 → LLM 精细分析（不确定，不硬判）
    return True, f"证据({chunk_count}条/{type_count}类)需LLM精细分析", None


# ══════════════════════════════════════════════════════════════════════
# 4. 报告生成 Observe
# ══════════════════════════════════════════════════════════════════════

def observe_report_generation(ctx: AgentContext) -> tuple[bool, str, Optional[str]]:
    """判断报告生成是否需要 LLM（激进 — 只有复杂才用LLM）。"""
    chains = ctx.evidence_chains
    if not chains:
        return False, "无证据链，模板报告", None

    statuses = {c.get("status", "") for c in chains}
    min_conf = min((c.get("confidence", 0) for c in chains), default=0)
    chain_count = len(chains)

    # 全部 pass 或 全部 reject → 模板
    if statuses <= {"pass", "reject"} and chain_count <= 2:
        return False, f"结论明确(status={statuses})，模板报告", None

    # 只有 review 且置信度 < 0.60 → 模板（不足以让LLM发挥）
    if statuses == {"review"} and min_conf < 0.60:
        return False, "虽需复核但证据太少，模板报告", None

    # review + 多链条 + 置信度中等 → LLM 撰写补证建议
    if "review" in statuses and chain_count >= 2:
        return True, "多链条需复核，LLM撰写针对性补证建议", None

    # mixed statuses（pass+reject混存）→ LLM
    if len(statuses) > 1:
        return True, "证据链结论不一，需要LLM综合研判", None

    return False, "模板报告", None


# ══════════════════════════════════════════════════════════════════════
# 统一 Observe 接口
# ══════════════════════════════════════════════════════════════════════

_OBSERVE_RESULTS: list[dict] = []


def observe(agent_name: str, ctx: AgentContext) -> tuple[bool, str, any]:
    """统一 Observe 入口。记录决策到全局日志。

    Returns:
        (should_use_llm, reason, fallback_result)
    """
    observers = {
        "element_extractor": observe_element_extraction,
        "knowledge_graph": observe_graph_building,
        "evidence_chain": observe_evidence_chain,
        "report_generator": observe_report_generation,
    }
    fn = observers.get(agent_name)
    if fn is None:
        return True, f"{agent_name}: 无Observe规则，默认走LLM", None

    should_llm, reason, fallback = fn(ctx)
    _OBSERVE_RESULTS.append({
        "agent": agent_name,
        "use_llm": should_llm,
        "reason": reason,
    })
    return should_llm, reason, fallback


def get_observe_log() -> list[dict]:
    """获取 Observe 决策日志。"""
    return list(_OBSERVE_RESULTS)


def clear_observe_log() -> None:
    """清空 Observe 日志（每次请求前调用）。"""
    _OBSERVE_RESULTS.clear()
