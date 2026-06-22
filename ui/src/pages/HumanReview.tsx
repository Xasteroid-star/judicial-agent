/** 人工复核模块 — architecture.md §5.7-5.8, §7 Agent */
import { useEffect, useState } from "react";

interface ReviewItem {
  id: string;
  type: "evidence" | "edge" | "element" | "report" | "annotation";
  title: string;
  detail: string;
  confidence: number;
  status: "pending" | "confirmed" | "rejected";
  reviewer?: string;
  review_time?: string;
  note?: string;
  retry_count?: number;
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
  const [retryResult, setRetryResult] = useState<any>(null);

  // 驳回意见框
  const [showRejectDialog, setShowRejectDialog] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const [rejecting, setRejecting] = useState(false);

  useEffect(() => {
    fetch("/api/reviews")
      .then((r) => r.json())
      .then((data) => setReviews(data.length > 0 ? data : MOCK_REVIEWS))
      .catch(() => setReviews(MOCK_REVIEWS));
  }, []);

  const handleConfirm = async (id: string) => {
    try {
      const res = await fetch(`/api/reviews/${id}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ review_id: id, action: "confirm", note: "" }),
      });
      if (res.ok) {
        setReviews((prev) =>
          prev.map((r) => (r.id === id ? { ...r, status: "confirmed" as const, reviewer: "审查员", review_time: new Date().toLocaleString() } : r))
        );
        setFeedback("已确认");
      } else {
        setFeedback(`确认失败: ${res.status}`);
      }
    } catch (e: any) {
      setFeedback(`请求失败: ${e.message}`);
    }
    setTimeout(() => setFeedback(""), 5000);
  };

  const handleReject = async () => {
    if (!selected) return;
    if (!rejectNote || rejectNote.trim().length < 5) {
      setFeedback("驳回需要写明补证方向（至少5字）");
      setTimeout(() => setFeedback(""), 4000);
      return;
    }
    setRejecting(true);
    setShowRejectDialog(false);
    try {
      const res = await fetch(`/api/reviews/${selected.id}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ review_id: selected.id, action: "驳回", note: rejectNote.trim() }),
      });
      const data = await res.json();
      setRejecting(false);

      if (!res.ok) {
        setFeedback(`驳回失败: ${res.status} ${data.detail || ""}`);
        setTimeout(() => setFeedback(""), 5000);
        return;
      }

      // 处理重检索结果
      if (data.status === "retrying" || data.status === "confirmed" || data.status === "needs_supplement") {
        setRetryResult(data);
        setFeedback(data.message || `重检索完成，置信度 ${data.new_confidence ? Math.round(data.new_confidence * 100) + "%" : "N/A"}`);
        setTimeout(() => setFeedback(""), 8000);

        // 更新本地状态
        setReviews((prev) =>
          prev.map((r) =>
            r.id === selected.id
              ? {
                  ...r,
                  status: data.status === "confirmed" ? "confirmed" : data.status === "needs_supplement" ? "rejected" : "rejected",
                  reviewer: "审查员",
                  review_time: new Date().toLocaleString(),
                  note: rejectNote.trim(),
                  confidence: data.new_confidence ?? r.confidence,
                }
              : r
          )
        );
      } else {
        // 直接驳回（原因太短等）
        setReviews((prev) =>
          prev.map((r) => (r.id === selected.id ? { ...r, status: "rejected" as const, reviewer: "审查员", review_time: new Date().toLocaleString(), note: rejectNote.trim() } : r))
        );
        setFeedback(data.warning || "已驳回");
        setTimeout(() => setFeedback(""), 3000);
      }
    } catch (e: any) {
      setRejecting(false);
      setFeedback(`请求失败: ${e.message}。请确认后端服务已启动。`);
      setTimeout(() => setFeedback(""), 5000);
    }
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

              {/* 重检索结果 */}
              {retryResult && retryResult.new_evidence && retryResult.new_evidence.length > 0 && (
                <div className="bg-blue-50 rounded-lg p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-medium text-blue-700">
                      重检索结果（第{retryResult.retry_round}轮）
                    </h4>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      (retryResult.new_confidence ?? 0) >= 0.85 ? "bg-green-100 text-green-700" :
                      (retryResult.new_confidence ?? 0) >= 0.70 ? "bg-yellow-100 text-yellow-700" : "bg-red-100 text-red-700"
                    }`}>
                      置信度 {Math.round((retryResult.new_confidence ?? 0) * 100)}%
                    </span>
                  </div>
                  {retryResult.message && (
                    <p className="text-xs text-blue-600">{retryResult.message}</p>
                  )}
                  <div className="space-y-1 max-h-[300px] overflow-auto">
                    {retryResult.new_evidence.map((ev: any, i: number) => (
                      <div key={i} className="bg-white rounded p-2 text-xs">
                        <span className="text-gray-400">[{ev.source_type}]</span>{" "}
                        <span className="text-gray-600">{ev.content_preview?.slice(0, 120)}</span>
                      </div>
                    ))}
                  </div>
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
                    onClick={() => { setShowRejectDialog(true); setRejectNote(""); setRetryResult(null); }}
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

      {/* 驳回意见对话框 */}
      {showRejectDialog && selected && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setShowRejectDialog(false)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-800">驳回 — 专家复核意见</h3>
              <button onClick={() => setShowRejectDialog(false)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
            </div>

            <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
              <p className="font-medium text-gray-700 mb-1">{selected.title}</p>
              <p className="text-xs">当前置信度: {Math.round(selected.confidence * 100)}%</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                驳回理由 <span className="text-red-500">*</span>
                <span className="text-gray-400 font-normal ml-2">（至少5字，写明需要补充的证据方向）</span>
              </label>
              <textarea
                autoFocus
                rows={4}
                value={rejectNote}
                onChange={e => setRejectNote(e.target.value)}
                placeholder="例如：缺少关键证人证言，需补充被害人陈述及银行流水记录；或：鉴定意见依据不足，需重新委托司法鉴定…"
                className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:ring-2 focus:ring-red-200 focus:border-red-400 outline-none resize-none"
              />
              <div className="flex justify-between mt-1">
                <span className={`text-xs ${rejectNote.trim().length < 5 ? "text-red-400" : "text-green-500"}`}>
                  已输入 {rejectNote.trim().length} 字{rejectNote.trim().length < 5 ? "（至少5字）" : ""}
                </span>
                {(selected.retry_count ?? 0) > 0 && (
                  <span className="text-xs text-yellow-600">已驳回 {selected.retry_count} 次，最多3次</span>
                )}
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setShowRejectDialog(false)}
                className="flex-1 py-2.5 border border-gray-300 text-gray-600 rounded-lg text-sm font-medium hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleReject}
                disabled={rejecting || rejectNote.trim().length < 5}
                className="flex-1 py-2.5 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:bg-red-300 disabled:cursor-not-allowed transition-colors"
              >
                {rejecting ? "驳回中..." : "确认驳回"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 加载状态 */}
      {rejecting && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 shadow-lg text-center">
            <div className="animate-spin w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full mx-auto mb-3" />
            <p className="text-sm text-gray-600">正在检索补充证据...</p>
          </div>
        </div>
      )}
    </div>
  );
}
