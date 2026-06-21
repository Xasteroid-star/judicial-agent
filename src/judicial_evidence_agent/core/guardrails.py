"""Guardrails — 防幻觉、注意力强制、循环控制。

所有 Agent 和 LLM 调用共享的约束规则。
参考：Anthropic RLHF safety guidelines + 司法场景特殊性。
"""

# ============================================================================
# 核心防幻觉系统提示词 — 注入所有 LLM 调用
# ============================================================================

ANTI_HALLUCINATION_SYSTEM_PROMPT = """
## 防幻觉规则（违反任何一条均为错误输出）

### 1. 严格基于材料
- 你只能使用【可用材料】中明确提供的信息。
- 【可用材料】中没有的信息 = 不存在。不得推测、补充、联想。
- 如果材料不足以支持某个结论，你必须明确说"现有材料不足以得出该结论"，
  并列出具体缺失哪些证据。严禁编造不存在的事实。

### 2. 每条结论绑定来源
- 每条结论后必须标注来源，格式为：[来源: {法条编号} | {证据ID}]
- 没有来源标注的结论被视为幻觉，必须删除。
- 来源必须真实存在于【可用材料】中，不得虚构文件名、法条号。

### 3. 区分事实与推测
- "材料显示" = 事实陈述
- "可能" / "推测" / "估计" = 禁止使用
- "待核实" = 允许，但必须说明核实方法

### 4. 诚实边界
- 你不知道的 = 说"不知道"
- 材料矛盾的 = 指出矛盾，不做选择
- 超出司法证据审查范围的 = 拒绝回答

### 5. 禁止编造法律条文
- 引用的法条必须完整出现在【可用材料】中。
- 不得概括、缩写、推测法条内容。
- 法条引用格式：指出具体条文编号 + 生效日期。
"""

# ============================================================================
# 注意力强制提示词 — 防止忽略检索结果
# ============================================================================

ATTENTION_FORCE_PROMPT = """
## 注意力规则

### 强制步骤（不可跳过）
1. 首先，完整阅读【可用材料】中的所有条目。
2. 对每条材料，判断与当前分析问题的相关性。
3. 标注每条材料的使用情况：
   - 已使用：该材料被用于支撑某个结论
   - 不相关：该材料与当前问题无关
   - 需补充：该材料提供了线索但信息不完整
4. 如果没有任何材料可以使用，输出"根据现有材料无法分析"并列出缺口。

### 禁止行为
- 跳过材料直接输出结论 ← 严重错误
- 只使用部分材料而忽略其他 ← 需要说明原因
- 使用材料中的信息但不标注来源 ← 严重错误
- 从材料中"概括"出材料不包含的结论 ← 幻觉
"""

# ============================================================================
# 循环控制 — 防止死循环 / 过度工具调用
# ============================================================================

MAX_RETRY_COUNT = 3
MAX_TOOL_CALLS_PER_AGENT = 5

LOOP_GUARD_PROMPT = """
## 循环控制规则

1. 如果同一查询已经检索 2 次且结果相同，停止检索，使用已有结果。
2. 如果生成的分析已包含所有检索到的材料，停止生成，输出最终报告。
3. 如果连续 2 次尝试都返回相同内容，立即停止，标记为"收敛"。
4. 严禁重新检索刚刚已经检索过的内容（除非用户明确换了新查询）。
"""

# ============================================================================
# 引用强制 — SuperMew 模式：必须用 [1][2][3] 标注来源
# ============================================================================

CITATION_ENFORCEMENT_PROMPT = """
## 引用规则（违反即为错误输出）

1. 基于检索到的材料回答时，必须使用 [1] [2] [3] 等序号标注来源。
2. 序号对应上文【可用材料】中的证据编号。
3. 没有来源标注的结论 = 幻觉，必须删除。
4. 如果引用多条材料，请写 [1][3] 或 [1][2][3]。
5. 如果你无法在材料中找到支撑某句话的依据，不要编造来源序号。

示例正确输出：
  根据鉴定意见[1]，被害人损伤程度为轻伤二级。证人张某证实看到王某持刀[2]。
"""

# ============================================================================
# 工具调用死循环守卫 — SuperMew 模式
# ============================================================================

TOOL_LOOP_GUARD_PROMPT = """
## 工具调用规则

1. 同一轮对话中最多调用一次知识库检索工具。
2. 收到检索结果后，必须立即基于结果生成最终回答，禁止再次调用任何工具。
3. 如果检索结果不足以回答问题，诚实回答"根据现有材料无法确定"，禁止反复检索。
4. 禁止用不同的关键词重复检索同一个问题。
"""

# ============================================================================
# 工作记忆 — SuperMew Persistent Note 模式
# ============================================================================


class WorkingMemory:
    """对话工作记忆 — 每轮后自动总结，下轮注入为 System Prompt。

    SuperMew 的核心机制：防止多轮对话中遗忘已讨论内容。
    """

    def __init__(self):
        self._note: str = ""

    def update(self, user_text: str, ai_response: str) -> None:
        """更新工作记忆：记录本轮关键结论。"""
        summary = f"用户问了「{user_text[:80]}」，回答涉及：{ai_response[:200]}"
        self._note = self._note[-2000:] + "\n" + summary if self._note else summary

    def as_system_message(self) -> str:
        """生成可注入 System Prompt 的工作记忆文本。"""
        if not self._note:
            return ""
        return (
            "【对话工作记忆 — 请参考以下历史以保持连贯，避免重复回答】\n"
            f"{self._note}"
        )

    def clear(self) -> None:
        self._note = ""


# 全局工作记忆实例
working_memory = WorkingMemory()


# ============================================================================
# 合成完整系统提示词
# ============================================================================


def build_guard_system_prompt(base_prompt: str = "") -> str:
    """构建完整防幻觉系统提示词（含 SuperMew 模式）。"""
    parts = [
        base_prompt,
        ANTI_HALLUCINATION_SYSTEM_PROMPT,
        CITATION_ENFORCEMENT_PROMPT,
        TOOL_LOOP_GUARD_PROMPT,
        ATTENTION_FORCE_PROMPT,
    ]
    return "\n\n".join(p for p in parts if p)


# ============================================================================
# 输出验证器
# ============================================================================


class OutputValidator:
    """对 LLM 输出进行后验检查。"""

    @staticmethod
    def check_citations(text: str, available_sources: list[str]) -> dict:
        """检查输出中的引用是否来自实际可用的来源。"""
        violations = []
        import re

        # 查找所有 [来源: ...] 标记
        citations = re.findall(r"\[来源[:：]\s*([^\]]+)\]", text)
        for cite in citations:
            cite_clean = cite.strip()
            found = any(s in cite_clean or cite_clean in s for s in available_sources)
            if not found:
                violations.append(f"虚构来源: {cite_clean}")

        return {
            "total_citations": len(citations),
            "violations": violations,
            "pass": len(violations) == 0,
        }

    @staticmethod
    def check_no_fabrication(text: str, available_text: str) -> list[str]:
        """检测 LLM 是否编造了材料中没有的事实。

        简化版：检查输出中的关键断言是否在可用材料中出现。
        """
        import re

        # 提取所有带数字/金额/人名的断言
        assertions = re.findall(
            r"(?:证实|显示|表明|认定|查明)[：:]*([^。；\n]{10,50})", text
        )
        violations = []
        available_simple = available_text.replace("\n", " ").replace("  ", " ")

        for a in assertions:
            # 检查核心关键词是否在材料中出现
            core = re.sub(r"[的得了着在地]", "", a)[:15]
            if core and core not in available_simple:
                violations.append(f"可能编造: {a[:60]}")

        return violations

    @staticmethod
    def check_loop(text: str, history: list[str]) -> bool:
        """检测是否陷入重复输出循环。"""
        if len(history) < 2:
            return False
        # 检查最近两次输出是否高度相似
        last = history[-1][:200] if history[-1] else ""
        prev = history[-2][:200] if history[-2] else ""
        if last and prev and last == prev:
            return True
        # 检查输出中是否有重复段落
        lines = text.split("\n")
        if len(lines) > 10:
            unique = len(set(line[:60] for line in lines if line.strip()))
            return unique < len(lines) * 0.3  # 少于30%唯一行 = 循环
        return False
