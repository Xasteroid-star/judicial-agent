"""卷宗解析 Agent — architecture.md §7

判断材料类型 → 调用 OCR/ASR/表格/视频解析工具 → 生成 EvidenceChunk。
当前 Demo 阶段直接接收预解析的材料。
"""

from judicial_evidence_agent.core.agents.base import BaseAgent, AgentContext


class DocketParserAgent(BaseAgent):
    """卷宗解析 Agent。

    职责：
    1. 识别材料类型（文书/扫描件/音频/视频/表格）
    2. 调用对应解析服务（OCR/ASR/表格解析）
    3. 输出统一 EvidenceChunk
    """

    name = "docket_parser"

    async def run(self, ctx: AgentContext) -> AgentContext:
        # Demo 阶段：直接标记已解析的材料
        ctx.material_ids = ["M-001", "M-002", "M-003", "M-004", "M-005"]
        ctx.processing_errors = []

        # 后期：遍历 materials，按类型路由到解析服务
        # for m in materials:
        #     if m.type == "scan": ocr_result = await ocr_service.process(m)
        #     elif m.type == "audio": asr_result = await asr_service.process(m)
        #     ...

        return ctx
