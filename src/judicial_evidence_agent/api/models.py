"""API Pydantic schemas — 请求/响应模型。

引用 core/contracts.py 中的领域模型，在此定义 API 层的输入输出格式。
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ============================================================================
# 案件
# ============================================================================


class CaseCreateRequest(BaseModel):
    case_name: str
    case_number: str
    case_type: str
    description: str = ""


class CaseResponse(BaseModel):
    case_id: UUID
    case_name: str
    case_number: str
    case_type: str
    description: str
    created_at: datetime
    updated_at: datetime


# ============================================================================
# 材料
# ============================================================================


class MaterialUploadResponse(BaseModel):
    material_id: UUID
    name: str
    type: str
    file_hash: str
    processing_status: str


# ============================================================================
# 证据链分析
# ============================================================================


class AnalysisRequest(BaseModel):
    case_id: UUID
    modalities: list[str] = Field(default_factory=lambda: ["text", "table", "image"])


class AnalysisStatus(BaseModel):
    stage: str  # parsing / extraction / graph / review / report
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = ""


class AnalysisResult(BaseModel):
    case_id: UUID
    materials_processed: int
    chunks_generated: int
    graph_nodes: int
    graph_edges: int
    confidence_summary: dict
    report_id: Optional[UUID] = None


# ============================================================================
# 图谱
# ============================================================================


class GraphDataResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


# ============================================================================
# 报告
# ============================================================================


class ReportResponse(BaseModel):
    report_id: UUID
    case_id: UUID
    title: str
    sections: list[dict]
    created_at: datetime
