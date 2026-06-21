/** 报告生成与查看 — architecture.md §5.8 */
import { useState } from "react";

const MOCK_REPORT = {
  report_id: "RPT-2024-001",
  title: "王某故意伤害案 — 证据链审查报告",
  created_at: "2024-08-12 16:30",
  sections: [
    {
      heading: "一、案件材料处理概况",
      content: `本案共接收材料5件：
- 受案登记表（文本文书，M-001）
- 现场勘查照片（图片，M-002）
- 询问笔录（文本文书，M-003）
- 讯问录音（音频，M-004，待处理）
- 银行流水（表格，M-005，待处理）

已完成 OCR 解析 2 件，要素抽取 3 件，生成证据片段 5 条。`,
    },
    {
      heading: "二、核心证据链分析",
      content: `证据链1：伤害事实
待证事实：李某损伤程度为轻伤二级
支撑证据：司法鉴定意见书（M-006，置信度 0.95）
法律依据：刑法第234条 故意伤害罪
置信度：0.85 ✓

证据链2：作案行为
待证事实：王某持木棍殴打李某
支撑证据：证人张某证言（M-007，置信度 0.78）
法律依据：刑法第234条
置信度：0.72 ⚠ 需补证

证据链3：作案工具
待证事实：木棍为作案工具
支撑证据：物证木棍（需 DNA 比对）
法律依据：刑诉法第50条 物证
置信度：0.65 ⚠ 缺鉴定意见`,
    },
    {
      heading: "三、对立证据与风险识别",
      content: `1. 王某主张刑讯逼供 — 现有材料无法核实，缺少讯问录音录像
   风险：依据《排除非法证据规定》第34条，不能排除非法取证可能的，应当排除
   建议：调取同步录音录像，进行体检记录比对

2. 银行流水中的转账记录 — 案发当日李某向未知账户转账5000元，备注"赔偿款"
   可能指向双方和解，影响故意伤害的主观故意认定
   建议：核实收款方身份及转账背景`,
    },
    {
      heading: "四、置信度审查说明",
      content: `综合置信度：0.78（需人工复核）
各维度得分：
- 来源可信度：0.85（物证来源清晰，证人身份可确认）
- 解析质量：0.78（OCR 准确率 98%，音频待处理）
- 要素抽取置信度：0.82（人物/时间/地点/行为已抽取）
- 检索命中质量：0.75（法条匹配准确，类案检索待补充）
- 图谱支撑强度：0.70（核心边已构建，缺失交叉验证）
- 证据一致性：0.80（主要证据指向一致）
- 模型自检评分：0.85

阈值判定：需复核（0.70-0.85 区间）`,
    },
    {
      heading: "五、补证与复核建议",
      content: `优先级1（直接影响定罪）：
1. 调取讯问同步录音录像（验证刑讯逼供主张）
2. 木棍 DNA 比对鉴定（确认作案工具）
3. 调取王某体检记录（核查非法取证）
4. 核实李某转账背景（排除和解可能）
5. 调取现场周边监控录像（寻找目击证据）

优先级2（完善证据链）：
6. 证人张某出庭作证安排
7. 伤情照片与鉴定意见书的比对说明
8. 王某前科记录查询`,
    },
    {
      heading: "六、主要溯源清单",
      content: `| 结论 | 来源 |
|------|------|
| 李某轻伤二级 | M-006 司法鉴定意见书 第1页 |
| 王某持木棍殴打 | M-007 证人张某证言 第1页第2段 |
| 刑讯逼供风险 | M-004 讯问录音（调取中） |
| 非法证据排除依据 | 排除非法证据规定第34条 |
| 故意伤害罪构成 | 刑法第234条 |
| 物证定义 | 刑诉法第50条第1项 |`,
    },
  ],
};

export function ReportView() {
  const [expanded, setExpanded] = useState<Set<number>>(new Set([0]));

  const toggle = (i: number) => {
    const next = new Set(expanded);
    next.has(i) ? next.delete(i) : next.add(i);
    setExpanded(next);
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-gray-800">{MOCK_REPORT.title}</h2>
        <p className="text-sm text-gray-400 mt-1">
          {MOCK_REPORT.report_id} · 生成时间: {MOCK_REPORT.created_at}
        </p>
      </div>

      <div className="space-y-3">
        {MOCK_REPORT.sections.map((section, i) => (
          <div key={i} className="bg-white rounded-lg border overflow-hidden">
            <button
              onClick={() => toggle(i)}
              className="w-full flex items-center justify-between p-4 text-left hover:bg-gray-50 transition-colors"
            >
              <h3 className="font-semibold text-gray-700 text-sm">{section.heading}</h3>
              <span className="text-gray-300 text-xs">{expanded.has(i) ? "收起" : "展开"}</span>
            </button>
            {expanded.has(i) && (
              <div className="px-4 pb-4 text-sm text-gray-600 leading-relaxed whitespace-pre-wrap border-t pt-3">
                {section.content}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-6 flex gap-3 justify-end">
        <button className="px-4 py-2 border rounded-lg text-sm text-gray-500 hover:bg-gray-50">
          导出 PDF
        </button>
        <button className="px-4 py-2 border rounded-lg text-sm text-gray-500 hover:bg-gray-50">
          打印
        </button>
      </div>
    </div>
  );
}
