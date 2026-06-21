"""PostgreSQL 数据库 schema — SQLAlchemy ORM 模型。

所有表通过 SQLAlchemy async engine 操作，与 FastAPI 集成。
图谱存储用关系表（无专门图数据库）。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ============================================================================
# 案件与材料
# ============================================================================


class CaseModel(Base):
    __tablename__ = "cases"

    case_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    case_name = Column(String(256), nullable=False)
    case_number = Column(String(128), nullable=False)
    case_type = Column(String(64), nullable=False)
    description = Column(Text, default="")
    source = Column(String(64), default="")  # cail2018 / pdp_bench / user_upload
    source_id = Column(String(128), default="")  # 原数据集ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MaterialModel(Base):
    __tablename__ = "materials"

    material_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PG_UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    name = Column(String(256), nullable=False)
    type = Column(String(32), nullable=False)
    source_org = Column(String(128), default="")
    collector = Column(String(64), default="")
    confidentiality_level = Column(String(16), default="medium")
    file_hash = Column(String(128), default="")
    file_path = Column(String(512), default="")
    version = Column(Integer, default=1)
    processing_status = Column(String(16), default="pending")
    received_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# 证据片段与要素
# ============================================================================


class EvidenceChunkModel(Base):
    __tablename__ = "evidence_chunks"

    chunk_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PG_UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    material_id = Column(PG_UUID(as_uuid=True), ForeignKey("materials.material_id"), nullable=False)
    modality = Column(String(16), nullable=False)  # text / image / audio / video / table
    content_text = Column(Text, default="")
    extracted_elements = Column(JSONB, default=dict)
    source_pointer = Column(JSONB, default=dict)
    confidence = Column(Float, default=0.0)
    model_version = Column(String(32), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class ExtractedElementModel(Base):
    __tablename__ = "extracted_elements"

    element_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_id = Column(PG_UUID(as_uuid=True), ForeignKey("evidence_chunks.chunk_id"), nullable=False)
    case_id = Column(PG_UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    category = Column(String(64), nullable=False)  # 人物/时间/地点/行为/金额等
    value = Column(String(256), nullable=False)
    source_pointer = Column(JSONB, default=dict)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# 知识图谱（PostgreSQL 关系表）
# ============================================================================


class GraphNodeModel(Base):
    __tablename__ = "graph_nodes"

    node_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PG_UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    node_type = Column(String(32), nullable=False)
    label = Column(String(256), nullable=False)
    properties = Column(JSONB, default=dict)
    source_chunk_id = Column(PG_UUID(as_uuid=True), ForeignKey("evidence_chunks.chunk_id"), nullable=True)
    created_by = Column(String(64), default="system")
    human_review_status = Column(String(16), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class GraphEdgeModel(Base):
    __tablename__ = "graph_edges"

    edge_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    from_node = Column(PG_UUID(as_uuid=True), ForeignKey("graph_nodes.node_id"), nullable=False)
    to_node = Column(PG_UUID(as_uuid=True), ForeignKey("graph_nodes.node_id"), nullable=False)
    relation_type = Column(String(32), nullable=False)
    confidence = Column(Float, default=0.0)
    source_chunk_id = Column(PG_UUID(as_uuid=True), ForeignKey("evidence_chunks.chunk_id"), nullable=True)
    created_by = Column(String(64), default="system")
    model_version = Column(String(32), default="")
    human_review_status = Column(String(16), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# 报告与审计
# ============================================================================


class ReportModel(Base):
    __tablename__ = "reports"

    report_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PG_UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    title = Column(String(256), nullable=False)
    sections = Column(JSONB, default=list)
    prompt_version = Column(String(32), default="")
    model_version = Column(String(32), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    log_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), default="")
    target_id = Column(PG_UUID(as_uuid=True), nullable=True)
    detail = Column(JSONB, default=dict)
    model_version = Column(String(32), default="")
    ip_address = Column(String(64), default="")
