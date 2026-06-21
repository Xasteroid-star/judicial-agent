/** 人工复核模块 — architecture.md §5.7-5.8, §7 Agent */
import { useEffect, useState } from "react";

interface ReviewItem {
  id: string;
  type: "evidence" | "edge" | "element" | "report";
  title: string;
  detail: string;
  confidence: number;
  status: "pending" | "confirmed" | "rejected";
  reviewer?: string;
  review_time?: string;
  note?: string;
}

const MOCK_REVIEWS: ReviewItem[] = [
  {
    id: "RV-001", type: "evidence", title: "证人张某证言可信度审查",
    detail: "张某系小区保安，与双方无利害关系，证言与其他证据吻合。但证言中时间描述模糊（当日下午3时许）。",
    confidence: 0.78, status: "pending",
  },
  {
    id: "RV-002", type: "edge", title: "木棍→殴打行为 证明关系",
    detail: "图谱中物证木棍直接关联到殴打行为的证明边。木棍上提取的DNA需与李某伤处比对。",
    confidence: 0.82, status: "pending",
  },
  {
    id: "RV-003", type: "evidence", title: "王某刑讯逼供主张",
    detail: "王某称遭疲劳讯问和威胁。现有材料缺少讯问录音录像、体检记录，无法核实。",
    confidence: 0.35, status: "pending",
  },
  {
    id: "RV-004", type: "element", title: "银行流水中的转账记录",
    detail: "李某账户在案发后向未知账户转账5000元，备注赔偿款。可能是和解赔偿，也可能是其他用途。",
    confidence: 0.70, status: "pending",
  },
  {
    id: "RV-005", type: "report", title: "证据链报告 — 补证建议部分",
    detail: "LLM 生成的补证建议包含10项。人工审核确认：7项合理，3项需调整优先级。",
    confidence: 0.85, status: "pending",
  },
];

const TYPE_ICONS: Record<string, string> = {
  evidence: "📋", edge: "🔗", element: "🏷️", report: "📝",
};
const TYPE_LABELS: Record<string, string> = {
  evidence: "证据", edge: "图谱边", element: "要素", report: "报告",
};

export function HumanReview() {
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    fetch("/api/reviews")
      .then((r) => r.json())
      .then((data) => setReviews(data.length > 0 ? data : MOCK_REVIEWS))
      .catch(() => setReviews(MOCK_REVIEWS));
  }, []);

  const handleConfirm = async (id: string) => {
    setReviews((prev) =>
      prev.map((r) => (r.id === id ? { ...r, status: "confirmed" as const, reviewer: "审查员", review_time: new Date().toLocaleString() } : r))
    );
    setFeedback(`已确认 ${id}`);
    setTimeout(() => setFeedback(""), 3000);
    try { await fetch(`/api/reviews/${id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ review_id: id, action: "confirm", note: "" }) }); } catch {}
  };

  const handleReject = async (id: string) => {
    const note = prompt("驳回理由：") || "";
    if (note === null) return;
    setReviews((prev) =>
      prev.map((r) => (r.id === id ? { ...r, status: "rejected" as const, reviewer: "审查员", review_time: new Date().toLocaleString(), note } : r))
    );
    setFeedback(`已驳回 ${id}`);
    setTimeout(() => setFeedback(""), 3000);
    try { await fetch(`/api/reviews/${id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ review_id: id, action: "reject", note }) }); } catch {}
  };

  const statusBadge = (s: string) => {
    switch (s) {
      case "confirmed": return <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700">已确认</span>;
      case "rejected": return <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">已驳回</span>;
      default: return <span className="text-xs px-2 py-0.5 rounded bg-yellow-100 text-yellow-700">待复核</span>;
    }
  };

  const pending = reviews.filter((r) => r.status === "pending").length;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        {feedback && (
          <div className="mb-4 px-4 py-2 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
            {feedback}
          </div>
        )}
        <h2 className="text-xl font-bold text-gray-800">
          人工复核
          {pending > 0 && (
            <span className="ml-2 text-sm font-normal text-yellow-600">({pending} 项待处理)</span>
          )}
        </h2>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 text-sm border rounded-lg text-gray-500 hover:bg-gray-50">
            全部确认
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 待复核列表 */}
        <div className="bg-white rounded-lg border">
          <div className="p-4 border-b font-semibold text-gray-700">
            复核列表 ({reviews.length})
          </div>
          <div className="divide-y max-h-[600px] overflow-auto">
            {reviews.map((r) => (
              <div
                key={r.id}
                onClick={() => setSelected(r)}
                className={`p-4 cursor-pointer transition-colors hover:bg-gray-50 ${
                  selected?.id === r.id ? "bg-blue-50 border-l-2 border-[var(--color-accent)]" : ""
                } ${r.status !== "pending" ? "opacity-50" : ""}`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span>{TYPE_ICONS[r.type]}</span>
                  <span className="text-xs text-gray-400">{r.id}</span>
                  {statusBadge(r.status)}
                </div>
                <p className="text-sm font-medium text-gray-800">{r.title}</p>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 h-1 bg-gray-100 rounded-full">
                    <div
                      className={`h-1 rounded-full ${
                        r.confidence >= 0.85 ? "bg-green-500" :
                        r.confidence >= 0.70 ? "bg-yellow-500" : "bg-red-500"
                      }`}
                      style={{ width: `${r.confidence * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400">{Math.round(r.confidence * 100)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 详情 */}
        <div className="lg:col-span-2">
          {selected ? (
            <div className="bg-white rounded-lg border p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs text-gray-400">{selected.id}</span>
                  <h3 className="font-semibold text-gray-800 mt-1">{selected.title}</h3>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  TYPE_LABELS[selected.type] ? "bg-gray-100 text-gray-500" : ""
                }`}>
                  {TYPE_LABELS[selected.type]}
                </span>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="text-sm font-medium text-gray-500 mb-2">审查内容</h4>
                <p className="text-sm text-gray-700 leading-relaxed">{selected.detail}</p>
              </div>

              <div className="flex items-center gap-2 text-sm">
                <span className="text-gray-400">置信度:</span>
                <span className={`font-medium ${
                  selected.confidence >= 0.85 ? "text-green-600" :
                  selected.confidence >= 0.70 ? "text-yellow-600" : "text-red-600"
                }`}>
                  {Math.round(selected.confidence * 100)}%
                </span>
              </div>

              {selected.reviewer && (
                <div className="text-xs text-gray-400 space-y-1 pt-2 border-t">
                  <p>复核人: {selected.reviewer}</p>
                  <p>复核时间: {selected.review_time}</p>
                  {selected.note && <p>驳回理由: {selected.note}</p>}
                </div>
              )}

              {selected.status === "pending" && (
                <div className="flex gap-3 pt-4 border-t">
                  <button
                    onClick={() => handleConfirm(selected.id)}
                    className="flex-1 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition-colors"
                  >
                    确认通过
                  </button>
                  <button
                    onClick={() => handleReject(selected.id)}
                    className="flex-1 py-2 border border-red-300 text-red-600 rounded-lg text-sm font-medium hover:bg-red-50 transition-colors"
                  >
                    驳回
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-lg border p-12 text-center text-gray-300">
              选择一项待复核内容查看详情
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
