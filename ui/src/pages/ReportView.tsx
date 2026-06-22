/** 报告查看 — architecture.md §5.8 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";

interface ReportItem {
  report_id: string;
  case_id: string;
  title: string;
  status: string;
  judgment: string;
  charges: string[];
  disputes: string[];
  summary: string;
  created_at: string;
}

interface ReportDetail {
  report_id: string;
  case_name: string;
  status: string;
  judgment: string;
  summary: string;
  charges: string[];
  disputes: string[];
  evidence_types: string[];
  articles: string[];
  retry_count: number;
  evidence: { content: string; type: string }[];
  review_history: { timestamp: string; action: string; note: string; new_confidence?: number }[];
}

const STATUS_LABELS: Record<string, string> = {
  confirmed: "已确认",
  rejected: "已驳回",
  needs_supplement: "需补证",
  empty: "暂无报告",
};

export function ReportView() {
  const { reportId } = useParams<{ reportId?: string }>();
  const navigate = useNavigate();

  // 列表模式
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(true);

  // 详情模式
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set([0]));

  useEffect(() => {
    if (reportId) {
      fetch(`/api/reports/${reportId}`)
        .then(r => r.json())
        .then(setDetail)
        .catch(() => {})
        .finally(() => setLoading(false));
    } else {
      fetch("/api/reports")
        .then(r => r.json())
        .then(data => setReports(Array.isArray(data) ? data : []))
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [reportId]);

  const toggle = (i: number) => {
    const next = new Set(expanded);
    next.has(i) ? next.delete(i) : next.add(i);
    setExpanded(next);
  };

  // ── 报告详情视图 ──
  if (reportId && detail) {
    const sections = buildSections(detail);
    return (
      <div className="max-w-4xl mx-auto">
        <button onClick={() => navigate("/report")} className="text-sm text-blue-600 hover:underline mb-4 inline-block">
          ← 返回报告列表
        </button>

        <div className="mb-6">
          <h2 className="text-xl font-bold text-gray-800">{detail.case_name} — 证据链审查报告</h2>
          <div className="flex gap-3 mt-2 text-sm text-gray-400">
            <span>{detail.report_id?.slice(0, 12)}...</span>
            <span className={`px-2 py-0.5 rounded text-xs ${
              detail.status === "confirmed" ? "bg-green-100 text-green-700" :
              detail.status === "needs_supplement" ? "bg-yellow-100 text-yellow-700" :
              "bg-red-100 text-red-700"
            }`}>{STATUS_LABELS[detail.status] || detail.status}</span>
            {detail.retry_count > 0 && <span>驳回重检 {detail.retry_count} 次</span>}
          </div>
        </div>

        <div className="space-y-3">
          {sections.map((section, i) => (
            <div key={i} className="bg-white rounded-lg border overflow-hidden">
              <button onClick={() => toggle(i)}
                className="w-full flex items-center justify-between p-4 text-left hover:bg-gray-50">
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

        {/* 复核历史 */}
        {detail.review_history.length > 0 && (
          <div className="mt-6 bg-white rounded-lg border p-4">
            <h3 className="font-semibold text-gray-700 text-sm mb-3">复核历史</h3>
            <div className="space-y-2">
              {detail.review_history.map((h, i) => (
                <div key={i} className="flex items-start gap-3 text-xs text-gray-500">
                  <span className="text-gray-300 shrink-0 w-32">{h.timestamp?.slice(0, 19)}</span>
                  <span className={`px-1.5 py-0.5 rounded ${
                    h.action.includes("confirm") ? "bg-green-50 text-green-600" : "bg-red-50 text-red-600"
                  }`}>
                    {h.action.includes("confirm") ? "确认" :
                     h.action.includes("retry") ? `重检索${h.action.match(/\d/)?.[0] || ""}` :
                     h.action.includes("reject") ? "驳回" : h.action}
                  </span>
                  {h.note && <span className="text-gray-400">{h.note.slice(0, 60)}</span>}
                  {h.new_confidence !== undefined && (
                    <span className="text-blue-500">置信度→{Math.round(h.new_confidence * 100)}%</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-6 flex gap-3 justify-end">
          <button className="px-4 py-2 border rounded-lg text-sm text-gray-500 hover:bg-gray-50">导出 PDF</button>
          <button className="px-4 py-2 border rounded-lg text-sm text-gray-500 hover:bg-gray-50">打印</button>
        </div>
      </div>
    );
  }

  // ── 报告列表视图 ──
  return (
    <div className="max-w-4xl mx-auto">
      <h2 className="text-xl font-bold text-gray-800 mb-6">审查报告</h2>

      {loading ? (
        <div className="text-center text-gray-400 py-12">加载中...</div>
      ) : reports.length === 0 ? (
        <div className="text-center text-gray-400 py-12">
          <p className="text-lg mb-2">暂无已完成的审查报告</p>
          <p className="text-sm">在「人工复核」页面确认或驳回案件后，报告将出现在此处</p>
        </div>
      ) : (
        <div className="space-y-2">
          {reports.filter(r => r.status !== "empty").map(r => (
            <div key={r.report_id}
              onClick={() => navigate(`/report/${r.report_id}`)}
              className="bg-white rounded-lg border p-4 cursor-pointer hover:border-blue-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium text-gray-800 text-sm">{r.title}</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    {r.report_id?.slice(0, 12)}... · {r.charges?.join("、") || "未标注罪名"}
                  </p>
                </div>
                <div className="text-right">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    r.status === "confirmed" ? "bg-green-100 text-green-700" :
                    r.status === "rejected" ? "bg-red-100 text-red-700" :
                    r.status === "needs_supplement" ? "bg-yellow-100 text-yellow-700" :
                    "bg-gray-100 text-gray-500"
                  }`}>
                    {STATUS_LABELS[r.status] || r.status}
                  </span>
                  {r.judgment && <p className="text-xs text-gray-400 mt-1 truncate max-w-[200px]">{r.judgment}</p>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** 从 API 数据构建报告段落 */
function buildSections(d: ReportDetail): { heading: string; content: string }[] {
  const sections: { heading: string; content: string }[] = [];

  sections.push({
    heading: "一、案件基本情况",
    content: [
      `案名: ${d.case_name}`,
      `罪名: ${d.charges?.join("、") || "未标注"}`,
      `争议点: ${d.disputes?.join("、") || "未标注"}`,
      `适用法条: ${d.articles?.join("、") || "未标注"}`,
      `复核结果: ${STATUS_LABELS[d.status] || d.status}`,
      d.judgment ? `判定说明: ${d.judgment}` : "",
      d.retry_count > 0 ? `驳回重检次数: ${d.retry_count}` : "",
    ].filter(Boolean).join("\n"),
  });

  if (d.summary) {
    sections.push({
      heading: "二、案情摘要",
      content: d.summary,
    });
  }

  if (d.evidence.length > 0) {
    sections.push({
      heading: `三、证据材料列表（共 ${d.evidence.length} 条）`,
      content: d.evidence.map((ev, i) =>
        `[${i + 1}] ${ev.type ? `[${ev.type}] ` : ""}${ev.content?.slice(0, 300)}${ev.content?.length > 300 ? "..." : ""}`
      ).join("\n\n"),
    });
  }

  if (d.review_history.length > 0) {
    sections.push({
      heading: "四、复核审查记录",
      content: d.review_history.map(h => {
        const action = h.action.includes("confirm") ? "确认" :
                       h.action.includes("retry") ? "驳回重检索" :
                       h.action.includes("reject") ? "驳回" : h.action;
        return `[${h.timestamp?.slice(0, 19)}] ${action} · ${h.note || ""}${h.new_confidence !== undefined ? ` · 置信度 ${Math.round(h.new_confidence * 100)}%` : ""}`;
      }).join("\n"),
    });
  }

  return sections;
}
