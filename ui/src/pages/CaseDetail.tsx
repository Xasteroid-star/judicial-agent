/** 案件详情 — 从 API 动态加载 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { EvidenceGraph } from "../components/EvidenceGraph";
import { ConfidencePanel } from "../components/ConfidencePanel";

interface CaseData {
  case_id: string;
  case_name: string;
  case_number: string;
  case_type: string;
  charge?: string;
  article?: string;
  fact?: string;
  evidence_list?: { type: string; name: string }[];
}

export function CaseDetail() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<CaseData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/cases/${caseId}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [caseId]);

  if (loading) return <div className="text-gray-400 p-8">加载中...</div>;
  if (!data) return <div className="text-gray-400 p-8">案件不存在</div>;

  return (
    <div>
      <button onClick={() => navigate("/")} className="text-sm text-[var(--color-accent)] mb-4 inline-block hover:underline">
        ← 返回案件列表
      </button>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-800">{data.case_name}</h2>
          <p className="text-sm text-gray-400 mt-1">
            {data.case_number} · {data.charge || data.case_type}
            {data.article && ` · 刑法第${data.article}条`}
          </p>
        </div>
        <button
          onClick={() => navigate(`/analysis?caseId=${caseId}`)}
          className="px-4 py-2 bg-[var(--color-accent)] text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          证据链分析
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 证据列表 */}
        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-semibold text-gray-700 mb-3">证据材料</h3>
          {data.evidence_list && data.evidence_list.length > 0 ? (
            <div className="space-y-2">
              {data.evidence_list.map((ev, i) => (
                <div key={i} className="flex items-center gap-3 text-sm p-2 rounded hover:bg-gray-50">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 shrink-0">{ev.type}</span>
                  <span className="text-gray-700">{ev.name}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">暂无证据材料</p>
          )}
        </div>

        {/* 案情摘要 */}
        <div className="lg:col-span-2 bg-white rounded-lg border p-4">
          <h3 className="font-semibold text-gray-700 mb-3">案情摘要</h3>
          <p className="text-sm text-gray-600 leading-relaxed">{data.fact || data.case_name}</p>
        </div>
      </div>
    </div>
  );
}
