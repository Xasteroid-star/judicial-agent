# 司法多模态证据链 Agent

面向公检法场景的证据材料接入、解析、图谱构建与可溯源报告生成。

## 快速启动

```bash
# 安装依赖
pip install -e .

# 构建向量索引（首次运行）
python scripts/build_vector_index.py

# 一键启动（前端 + 后端）
start.bat

# 浏览器打开
# http://localhost:5173
```

或者分别启动：

```bash
# 后端 (端口 9091)
python server.py

# 前端 (端口 5173)
cd ui && npm install && npm run dev
```

## 页面功能

| 页面 | 路由 | 功能 |
|------|------|------|
| 案件管理 | `/` | 浏览案件列表，查看案件详情和关联证据 |
| 卷宗接入 | `/materials` | 查看已登记卷宗材料，支持上传 |
| 证据片段 | `/evidence` | 搜索/查看证据片段，含要素抽取和溯源指针 |
| 证据链分析 | `/analysis` | **核心**：选择案件 → 输入分析问题 → 生成报告 |
| 人工复核 | `/review` | 审查低置信度项，确认/驳回，驳回触发重检索 |
| 报告查看 | `/report` | 查看已完成的审查报告，含复核历史 |

## 分析模式

| 模式 | 引擎 | 耗时 | 适用场景 |
|------|------|------|----------|
| ⚡ 快速 | 规则引擎（关键词+正则+模板） | < 1s | 快速浏览、初步筛查 |
| 🧠 深度 | DeepSeek LLM | ~30s | 正式审查、精细分析 |

**快速模式**使用规则引擎：正则提取要素 → 关键词匹配证据类型 → 模板生成报告。
**深度模式**走完整 8-Agent 流水线：4 次 LLM 调用（要素抽取 + 知识图谱 + 证据链分析 + 报告生成）。

## 分析流水线

```
卷宗解析 → 要素抽取 ∥ RAG检索 → 知识图谱 → 证据链分析 → 置信度审查 → 报告生成 → 人工复核
```

| 阶段 | Agent | 职责 |
|------|-------|------|
| 1 | 卷宗解析 | 识别材料类型，标记处理状态 |
| 2 | 要素抽取 ∥ RAG检索 | 并行：提取人物/时间/地点/证据类型/争议；BGE向量检索法条+案例 |
| 3 | 知识图谱 | 构建 4 层图谱：法律要件 → 待证事实 → 证据要素 → 原始材料 |
| 4 | 证据链分析 | 判断 chain_status (pass/review/reject)，计算置信度 |
| 5 | 置信度审查 | 7 维加权评分 |
| 6 | 报告生成 | 六段式公诉风格审查报告 |
| 7 | 人工复核 | 生成待复核项列表 |

## 置信度计算

7 维度加权：

| 维度 | 权重 | 含义 |
|------|------|------|
| 来源可信度 | 20% | 证据来源是否清晰、可追溯 |
| 解析质量 | 15% | OCR/ASR 解析准确度 |
| 要素抽取置信度 | 15% | 司法要素提取的可信度 |
| 检索命中质量 | 15% | RAG 检索结果的相关性 |
| 图谱支撑强度 | 20% | 图谱节点和边的完整程度 |
| 一致性评分 | 10% | 证据之间的一致性 |
| 模型自检评分 | 5% | 各维度方差反映的稳定性 |

阈值：
- ≥ 0.85 → **通过**，可进入报告
- 0.70 ~ 0.85 → **需复核**
- 0.50 ~ 0.70 → **存疑**
- < 0.50 → **驳回**

## 驳回→重检索闭环

```
人工驳回（附补证方向）
  │
  ├─ 驳回原因注入查询 + 排除已见 chunk
  ├─ BGE 向量重检索
  ├─ 重算置信度
  ├─ ≥0.85 → 自动确认通过
  ├─ 0.70~0.85 → 返回新证据，可继续驳回（最多3轮）
  └─ 3轮不达标 → 标记 needs_supplement（需补充新材料）
```

每步操作写入 `audit_logs` 表。

## 目录结构

```
judicial-evidence-agent/
├── src/judicial_evidence_agent/
│   ├── core/                    # 纯 Python 核心（不依赖 api/ui）
│   │   ├── contracts.py         # 全部数据模型（Pydantic）
│   │   ├── evidence_chain.py    # RAG：BGE 向量检索 + 混合检索
│   │   ├── llm.py               # DeepSeek API 客户端（Anthropic 协议）
│   │   ├── graph.py             # networkx 图谱算法
│   │   ├── guardrails.py        # 防幻觉提示词 + 循环控制
│   │   ├── config.py            # 环境变量配置
│   │   └── agents/              # 7 个 Agent
│   │       ├── docket_parser.py
│   │       ├── element_extractor.py
│   │       ├── rag_retriever.py
│   │       ├── knowledge_graph.py
│   │       ├── evidence_chain.py
│   │       ├── confidence_reviewer.py
│   │       ├── report_generator.py
│   │       └── human_review.py
│   └── api/
│       └── main.py              # FastAPI 路由
├── ui/                          # React 前端
│   └── src/pages/
│       ├── CaseList.tsx
│       ├── CaseDetail.tsx
│       ├── MaterialUpload.tsx
│       ├── EvidenceViewer.tsx
│       ├── Analysis.tsx          # 证据链分析（模式切换）
│       ├── HumanReview.tsx       # 人工复核（驳回意见框）
│       └── ReportView.tsx        # 报告列表/详情
├── data/
│   ├── judicial_evidence.db     # SQLite 数据库
│   └── bge_index/               # BGE 向量索引
├── scripts/
│   ├── build_vector_index.py    # 构建向量索引
│   ├── import_cases.py          # 导入案件数据
│   └── label_cases.py           # 标注案件
├── eval/
│   ├── harness.py               # 评测框架
│   └── langsmith_eval.py        # LangSmith 评测
├── server.py                    # 后端启动入口
├── start.bat                    # 一键启动（Windows）
└── .env                         # 环境变量（API key 等）
```

## 评测

```bash
# LangSmith 评测
python eval/langsmith_eval.py --dataset "Judicial Evidence Golden Cases v2" --experiment "experiment-name"
```

## 技术栈

- **后端**: FastAPI + Uvicorn
- **LLM**: DeepSeek V4（Anthropic 协议兼容）
- **向量**: BGE (BAAI/bge-small-zh-v1.5) + Chroma
- **图谱**: networkx（计算）+ Cytoscape.js（前端可视化）
- **数据库**: SQLite（开发）/ PostgreSQL + pgvector（生产）
- **前端**: React + Vite + Tailwind CSS
- **评测**: LangSmith
