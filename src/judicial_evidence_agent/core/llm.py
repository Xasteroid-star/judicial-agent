"""LLM client — 大模型调用薄接口。

参考 Patchwork-Assurance 模式：一个瘦接口包装 Anthropic SDK，
内置防幻觉 guardrails，所有调用自动注入安全规则。

所有 LLM 调用通过 LangSmith @traceable 自动上报 tracing。
"""

from __future__ import annotations

# load_dotenv() 必须先于 langsmith import，确保 LANGCHAIN_* 环境变量就绪
from judicial_evidence_agent.core.config import settings  # noqa: F401 — triggers load_dotenv()

from anthropic import Anthropic
from langsmith import traceable

from judicial_evidence_agent.core.guardrails import (
    ANTI_HALLUCINATION_SYSTEM_PROMPT,
    ATTENTION_FORCE_PROMPT,
    OutputValidator,
    working_memory,
)

# 默认注入的防幻觉提示词
DEFAULT_GUARD_PROMPT = ANTI_HALLUCINATION_SYSTEM_PROMPT


class LLMClient:
    """LLM 客户端 — 自动注入防幻觉 guardrails。

    使用方式：
        client = LLMClient()
        response = await client.generate(prompt, system="你是法官助理...")
    """

    def __init__(self, model: str | None = None):
        import os
        api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        self._client = Anthropic(
            api_key=api_key,
            base_url=settings.anthropic_base_url,
        )
        self.model = model or settings.anthropic_model
        self._call_history: list[str] = []  # 循环检测
        self._retry_count = 0

    @traceable(run_type="llm", name="LLM.generate")
    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """调用 LLM 生成文本（自动注入防幻觉规则）。"""
        # 强制注入 guardrails + 工作记忆
        guard_system = DEFAULT_GUARD_PROMPT
        parts = [p for p in [system, working_memory.as_system_message(), guard_system] if p]
        full_system = "\n\n".join(parts)

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},  # DeepSeek: 禁用思考模式，直接输出
        }
        kwargs["system"] = full_system

        response = self._client.messages.create(**kwargs)
        # 兼容 DeepSeek thinking blocks + 标准 Anthropic text blocks
        # DeepSeek 返回格式: [ThinkingBlock, TextBlock] 或单独 TextBlock
        text = ""
        for block in response.content:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text = getattr(block, "text", "") or ""
            elif block_type == "thinking":
                # DeepSeek thinking block，取 thinking 内容作为 fallback
                if not text:
                    text = getattr(block, "thinking", "") or ""
        if not text and response.content:
            # 最后的 fallback
            last = response.content[-1]
            text = getattr(last, "text", "") or getattr(last, "thinking", "") or str(last)

        # 循环检测
        if OutputValidator.check_loop(text, self._call_history):
            self._retry_count += 1
            if self._retry_count >= 3:
                return "[循环终止] 模型陷入重复输出，已停止。请调整查询后重试。"
        else:
            self._retry_count = 0
        self._call_history.append(text)
        if len(self._call_history) > 10:
            self._call_history = self._call_history[-10:]

        # 更新工作记忆（SuperMew Persistent Note 模式）
        working_memory.update(prompt[:200], text[:200])

        return text

    @traceable(run_type="llm", name="LLM.generate_with_citations")
    async def generate_with_citations(
        self,
        prompt: str,
        retrieved_chunks: list[dict],
        system: str = "",
        max_tokens: int = 4096,
    ) -> str:
        """生成文本并强制引用来源。

        将检索到的证据片段注入 prompt，要求模型引用具体来源指针。
        """
        context = self._format_context(retrieved_chunks)
        full_prompt = (
            f"## 证据材料\n\n{context}\n\n"
            f"## 任务\n\n{prompt}\n\n"
            "要求：每个结论必须附带来源引用（材料ID、页码、行号等）。"
            "如果证据不足以得出结论，请说明需要补充哪些材料。"
        )
        return await self.generate(full_prompt, system=system, max_tokens=max_tokens)

    @staticmethod
    def _format_context(chunks: list[dict]) -> str:
        lines = []
        for i, chunk in enumerate(chunks, 1):
            src = chunk.get("source_pointer", {})
            lines.append(
                f"[{i}] 材料 {src.get('material_id', '?')}"
                f" | 页 {src.get('page', '?')}"
                f" | 行 {src.get('line_number', '?')}"
            )
            lines.append(f"    {chunk.get('content_text', '')[:500]}")
            lines.append("")
        return "\n".join(lines)


class StubLLM(LLMClient):
    """用于 CI / 离线测试的 LLM 桩。不调用真实 API。"""

    def __init__(self):
        pass  # 跳过 Anthropic 初始化

    async def generate(self, prompt: str, **kwargs) -> str:
        return f"[STUB] This is a canned response for testing."

    async def generate_with_citations(self, prompt: str, retrieved_chunks, **kwargs) -> str:
        return f"[STUB] Canned response with {len(retrieved_chunks)} citations."
