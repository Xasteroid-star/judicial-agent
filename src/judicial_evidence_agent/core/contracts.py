"""Core contracts — 领域数据模型。

本文件定义系统所有核心数据结构。API 层的 Pydantic schema 引用此处的定义，
不重复声明。参考 architecture.md §5 各模块设计。
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ============================================================================
# 枚举类型
# ============================================================================


class MaterialType(str, Enum):
    """卷宗材料类型（architecture.md §5.1）"""

    DOCUMENT = "document"  # 文本文书
    SCAN = "scan"  # 扫描件
    IMAGE = "image"  # 图片
    VIDEO = "video"  # 视频
    AUDIO = "audio"  # 音频
    TABLE = "table"  # 表格
    CHAT_RECORD = "chat_record"  # 聊天记录
    DIGITAL_FORENSIC = "digital_forensic"  # 电子数据检查材料


class Modality(str, Enum):
    """证据片段模态（architecture.md §5.2）"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TABLE = "table"


class ConfidentialityLevel(str, Enum):
    """保密级别"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    TOP_SECRET = "top_secret"


class ProcessingStatus(str, Enum):
    """处理状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RelationType(str, Enum):
    """图谱边关系类型（architecture.md §5.5）"""

    PROVES = "证明"
    REFUTES = "反驳"
    CORROBORATES = "补强"
    CONFLICTS = "冲突"
    DERIVED_FROM = "来源于"
    OCCURRED_AT = "发生于"
    RELATED_TO = "关联于"
    SAME_SUBJECT = "同一主体"
    AMOUNT_MATCH = "金额一致"
    AMOUNT_CONFLICT = "金额冲突"
    TIME_ADJACENT = "时间相邻"
    NEEDS_SUPPLEMENT = "需要补证"
    HUMAN_CONFIRMED = "人工确认"
    HUMAN_REJECTED = "人工驳回"


class NodeType(str, Enum):
    """图谱节点类型（architecture.md §5.5）"""

    CASE = "Case"
    LEGAL_ELEMENT = "LegalElement"
    FACT = "Fact"
    EVIDENCE = "Evidence"
    EVIDENCE_CHUNK = "EvidenceChunk"
    PERSON = "Person"
    TIME = "Time"
    LOCATION = "Location"
    ACTION = "Action"
    AMOUNT = "Amount"
    ACCOUNT = "Account"
    MATERIAL = "Material"
    RISK = "Risk"


class ReviewStatus(str, Enum):
    """人工复核状态"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    NEEDS_SUPPLEMENT = "needs_supplement"


# ============================================================================
# 案件与材料
# ============================================================================


class Case(BaseModel):
    """案件"""

    case_id: UUID = Field(default_factory=uuid4)
    case_name: str
    case_number: str
    case_type: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Material(BaseModel):
    """卷宗材料（architecture.md §5.1 登记字段）"""

    material_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    name: str
    type: MaterialType
    source_org: str = ""
    collector: str = ""
    received_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    confidentiality_level: ConfidentialityLevel = ConfidentialityLevel.MEDIUM
    file_hash: str = ""
    file_path: str = ""
    version: int = 1
    processing_status: ProcessingStatus = ProcessingStatus.PENDING


# ============================================================================
# 证据片段与要素
# ============================================================================


class SourcePointer(BaseModel):
    """证据溯源指针（architecture.md §8）

    每个结论必须能回到此指针所指位置。
    """

    material_id: UUID
    page: Optional[int] = None
    paragraph: Optional[int] = None
    line_number: Optional[int] = None
    table_row: Optional[int] = None
    table_column: Optional[str] = None
    image_region: Optional[str] = None  # e.g. "x:100,y:200,w:300,h:150"
    video_timestamp: Optional[str] = None  # e.g. "00:03:45.200"
    audio_timestamp: Optional[str] = None


class EvidenceChunk(BaseModel):
    """统一证据片段（architecture.md §5.2）"""

    model_config = {"protected_namespaces": ()}

    chunk_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    material_id: UUID
    modality: Modality
    content_text: str
    extracted_elements: dict = Field(default_factory=dict)
    source_pointer: SourcePointer
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model_version: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExtractedElement(BaseModel):
    """司法要素（architecture.md §5.3）"""

    element_id: UUID = Field(default_factory=uuid4)
    chunk_id: UUID
    case_id: UUID
    category: str  # 人物、时间、地点、行为、金额、物品、账号等
    value: str
    source_pointer: SourcePointer
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# 知识图谱
# ============================================================================


class GraphNode(BaseModel):
    """图谱节点（architecture.md §5.5）"""

    node_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    node_type: NodeType
    label: str
    properties: dict = Field(default_factory=dict)
    source_chunk_id: Optional[UUID] = None
    created_by: str = "system"
    human_review_status: ReviewStatus = ReviewStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GraphEdge(BaseModel):
    """图谱边（architecture.md §5.5）"""

    model_config = {"protected_namespaces": ()}

    edge_id: UUID = Field(default_factory=uuid4)
    from_node: UUID
    to_node: UUID
    relation_type: RelationType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_chunk_id: Optional[UUID] = None
    created_by: str = "system"
    model_version: str = ""
    human_review_status: ReviewStatus = ReviewStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# 置信度
# ============================================================================


class ConfidenceReview(BaseModel):
    """置信度审查（architecture.md §5.7）"""

    model_config = {"protected_namespaces": ()}

    review_id: UUID = Field(default_factory=uuid4)
    chunk_id: Optional[UUID] = None
    edge_id: Optional[UUID] = None
    source_credibility: float = Field(default=0.0, ge=0.0, le=1.0)
    parse_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    retrieval_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    graph_support: float = Field(default=0.0, ge=0.0, le=1.0)
    consistency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    model_self_check: float = Field(default=0.0, ge=0.0, le=1.0)
    final_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    threshold_result: str = ""  # pass / review / uncertain / reject
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def compute_final(self) -> float:
        """加权计算最终置信度（architecture.md §5.7 权重）"""
        self.final_confidence = (
            self.source_credibility * 0.20
            + self.parse_quality * 0.15
            + self.extraction_confidence * 0.15
            + self.retrieval_quality * 0.15
            + self.graph_support * 0.20
            + self.consistency_score * 0.10
            + self.model_self_check * 0.05
        )
        self.threshold_result = self._classify()
        return self.final_confidence

    def _classify(self) -> str:
        if self.final_confidence >= 0.85:
            return "pass"
        elif self.final_confidence >= 0.70:
            return "review"
        elif self.final_confidence >= 0.50:
            return "uncertain"
        else:
            return "reject"


# ============================================================================
# 报告
# ============================================================================


class Report(BaseModel):
    """可溯源审查报告（architecture.md §5.8）"""

    model_config = {"protected_namespaces": ()}

    report_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    title: str
    sections: list["ReportSection"] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model_version: str = ""
    prompt_version: str = ""


class ReportSection(BaseModel):
    """报告段落，每段绑定来源"""

    section_id: UUID = Field(default_factory=uuid4)
    heading: str
    content: str
    source_pointers: list[SourcePointer] = Field(default_factory=list)
    confidence: Optional[float] = None


# ============================================================================
# 审计
# ============================================================================


class AuditLog(BaseModel):
    """审计日志（architecture.md §6.5）"""

    model_config = {"protected_namespaces": ()}

    log_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    action: str  # upload / model_call / retrieval / graph_change / report / human_review
    target_type: str = ""  # material / chunk / edge / report
    target_id: Optional[UUID] = None
    detail: dict = Field(default_factory=dict)
    model_version: str = ""
    ip_address: str = ""
