"""LLM client — 大模型调用薄接口。

参考 Patchwork-Assurance 模式：一个瘦接口包装 Anthropic SDK，
内置防幻觉 guardrails，所有调用自动注入安全规则。
"""

from __future__ import annotations

from anthropic import Anthropic

from judicial_evidence_agent.core.config import settings
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
        }
        kwargs["system"] = full_system

        response = self._client.messages.create(**kwargs)
        # 兼容 DeepSeek thinking blocks + 标准 Anthropic text blocks
        text = ""
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text = block.text
                break
            if hasattr(block, "type") and block.type == "text":
                text = block.text
                break
        if not text:
            text = str(response.content[0]) if response.content else ""

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
