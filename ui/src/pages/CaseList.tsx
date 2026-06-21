import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { CaseItem } from "../lib/api";

const MOCK_CASES: CaseItem[] = [
  { case_id: "1", case_name: "王某故意伤害案", case_number: "京301刑初1号", case_type: "刑事", charge: "故意伤害罪", decision_type: "P", created_at: "2024-08-15" },
  { case_id: "2", case_name: "李某诈骗案", case_number: "沪201刑初2号", case_type: "刑事", charge: "诈骗罪", decision_type: "IENP", created_at: "2024-07-20" },
  { case_id: "3", case_name: "张某帮信罪案", case_number: "粤501刑初3号", case_type: "刑事", charge: "帮助信息网络犯罪活动罪", decision_type: "P", created_at: "2024-06-10" },
];

const DECISION_LABELS: Record<string, string> = {
  P: "起诉", IENP: "存疑不起诉", DNP: "酌定不起诉", SNP: "法定不起诉",
};
const DECISION_COLORS: Record<string, string> = {
  P: "bg-red-100 text-red-700",
  IENP: "bg-yellow-100 text-yellow-700",
  DNP: "bg-blue-100 text-blue-700",
  SNP: "bg-gray-100 text-gray-600",
};

export function CaseList() {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    fetch("/api/cases")
      .then((r) => r.json())
      .then(setCases)
      .catch(() => setCases(MOCK_CASES));
  }, []);

  const filtered = search.trim()
    ? cases.filter((c) =>
        c.case_name.includes(search) ||
        (c.charge || "").includes(search) ||
        c.case_number.includes(search)
      )
    : cases;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-800">案件列表</h2>
        <span className="text-sm text-gray-400">
          {filtered.length}/{cases.length} 件
        </span>
      </div>

      {/* 搜索 */}
      <div className="mb-4">
        <input
          className="w-full border rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none bg-white"
          placeholder="搜索案件名称、罪名、案号..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="grid gap-3">
        {filtered.map((c) => (
          <div
            key={c.case_id}
            onClick={() => navigate(`/case/${c.case_id}`)}
            className="bg-white rounded-lg border p-4 hover:shadow-md cursor-pointer transition-shadow flex items-center justify-between"
          >
            <div>
              <h3 className="font-semibold text-gray-800">{c.case_name}</h3>
              <p className="text-sm text-gray-400 mt-1">
                {c.case_number} · {c.charge}
              </p>
            </div>
            <div className="flex items-center gap-3">
              {c.decision_type && (
                <span className={`text-xs px-2 py-1 rounded-full font-medium ${DECISION_COLORS[c.decision_type]}`}>
                  {DECISION_LABELS[c.decision_type] || c.decision_type}
                </span>
              )}
              <span className="text-xs text-gray-300">{c.created_at}</span>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="text-center text-gray-300 py-12">
            {search ? "没有匹配的案件" : "暂无案件数据"}
          </div>
        )}
      </div>
    </div>
  );
}
