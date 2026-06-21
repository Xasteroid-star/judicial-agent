# CLAUDE.md — 司法多模态证据链 Agent

Operating manual for AI coding agents in this repo.

## 项目定位

面向公检法场景的多模态证据链 Agent。辅助办案人员完成卷宗材料接入、解析、量化、证据链构建、
冲突识别、置信度审查和可溯源报告生成。

核心原则：
- 任何结论必须绑定原始证据来源
- 模型生成内容不得脱离卷宗、法条、规则和图谱来源
- 低置信度结论不得直接进入证据链报告
- 人工复核结果应反向更新图谱、样本和评测集

## 架构概览

```
React UI (Vite + Tailwind + Cytoscape.js)
        │
   FastAPI (REST + SSE)
        │
   ┌────┼──────────────┐
   │    │              │
  core/ (纯 Python    处理服务
  证据链逻辑)         (OCR/ASR/视频等)
   │    │
   │  LangGraph (Agent 编排)
   │
   ├── PostgreSQL + pgvector (业务数据 + 向量索引 + 图谱存储)
   └── MinIO (原始文件存储)
```

## 架构 invariants（不可违反）

1. **`core/` 包只向内 import。** `core` 从不 import `api/` 或 `ui/`。API 导入 `core`。
   依赖箭头单向。
2. **所有证据结论必须绑定来源。** 每条 EvidenceChunk 必须携带 `source_pointer`
   （页码、行号、时间戳等）。
3. **图谱存储用 PostgreSQL 关系表。** nodes + edges 两张表，不引入专门的图数据库。
   `networkx` 在 core 层做图算法，Cytoscape.js 在前端做可视化。
4. **MVP 先做规则 + LLM + RAG + 图谱。** GNN 阶段三才引入，不要在 MVP 阶段构建。
5. **审计日志记录所有关键操作。** 文件上传、模型调用、检索结果、图谱变更、报告生成、
   人工确认/驳回。

## 目录结构

```
src/judicial_evidence_agent/
  core/           # 纯 Python 核心：数据模型、图谱、RAG、Agent、报告
  api/            # FastAPI 薄壳：路由、Pydantic schema
  ui/             # React 前端（后期）
tests/
corpus/           # 法条、证据规则、司法解释等参考语料
docs/
```

## 技术栈

- **后端**: FastAPI + Uvicorn
- **Agent 编排**: LangGraph
- **数据库**: PostgreSQL + pgvector（业务数据 + 向量 + 图谱统一存储）
- **图计算**: networkx（core 层算法）
- **向量**: Chroma（本地开发）/ pgvector（生产）
- **LLM**: Claude API（通过 `core/llm.py` 薄接口）
- **文件存储**: MinIO（S3 兼容）
- **前端**: React + Vite + Tailwind CSS + Cytoscape.js

## 惯例

- Python 全栈，前端 React 是唯一非 Python 组件
- `ruff` (lint + format) + `pytest`，保持绿色
- Git 由用户自己操作，不自动 commit/push
- 所有 Pydantic 模型定义在 `core/contracts.py`，API schema 引用之
