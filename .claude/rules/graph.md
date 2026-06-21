# Rule: 知识图谱

- **不使用专门的图数据库。** 图谱存储使用 PostgreSQL 关系表（graph_nodes + graph_edges）。
  图计算使用 networkx，前端可视化使用 Cytoscape.js。
- **四层图谱结构不可合并。** 法律要件层 → 待证事实层 → 证据要素层 → 原始材料层，
  每层独立，跨层关联通过边连接。
- **边的 confidence 字段必填。** 每条边初始化时必须有置信度值，不允许 null。
- **冲突和反驳边必须醒目。** 在报告和前端可视化中，CONFLICTS 和 REFUTES 边
  应红色高亮，方便审查人员快速定位。
- **图谱版本化。** graph_versions 表记录每次对图谱的修改，支持回溯。
