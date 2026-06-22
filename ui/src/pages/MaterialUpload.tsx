/** 卷宗接入模块 — architecture.md §5.1 */
import { useEffect, useState } from "react";

interface Material {
  material_id: string;
  case_id: string;
  name: string;
  type: string;
  source_org: string;
  collector: string;
  confidentiality_level: string;
  file_hash: string;
  processing_status: string;
  created_at: string;
}

const CONF_LABELS: Record<string, string> = {
  low: "低", medium: "中", high: "高", top_secret: "绝密",
};

export function MaterialUpload() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/materials")
      .then(r => r.json())
      .then(data => setMaterials(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const statusColor = (s: string) =>
    s === "completed" ? "bg-green-100 text-green-700" : s === "processing" ? "bg-blue-100 text-blue-700" : "bg-yellow-100 text-yellow-700";
  const statusLabel = (s: string) =>
    s === "completed" ? "已完成" : s === "processing" ? "处理中" : "待处理";

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-800">卷宗接入</h2>
        <button className="px-4 py-2 bg-[var(--color-accent)] text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          + 上传材料
        </button>
      </div>

      <div className="bg-white rounded-lg border border-dashed p-8 text-center mb-6 hover:border-[var(--color-accent)] transition-colors cursor-pointer">
        <p className="text-gray-400 text-sm">拖放文件到此处，或点击上方按钮选择文件</p>
        <p className="text-gray-300 text-xs mt-1">支持：PDF、DOCX、XLSX、JPG、PNG、MP3、MP4、ZIP</p>
      </div>

      {loading ? (
        <div className="text-center text-gray-400 py-12">加载中...</div>
      ) : error ? (
        <div className="text-center text-red-400 py-12">加载失败: {error}</div>
      ) : materials.length === 0 ? (
        <div className="text-center text-gray-400 py-12">暂无材料，请上传</div>
      ) : (
        <div className="bg-white rounded-lg border">
          <div className="p-4 border-b">
            <h3 className="font-semibold text-gray-700">已登记材料 ({materials.length})</h3>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b">
                  <th className="p-3 font-medium">材料名称</th>
                  <th className="p-3 font-medium">类型</th>
                  <th className="p-3 font-medium">来源</th>
                  <th className="p-3 font-medium">采集人</th>
                  <th className="p-3 font-medium">密级</th>
                  <th className="p-3 font-medium">哈希</th>
                  <th className="p-3 font-medium">状态</th>
                  <th className="p-3 font-medium">登记时间</th>
                </tr>
              </thead>
              <tbody>
                {materials.map((m) => (
                  <tr key={m.material_id} className="border-b hover:bg-gray-50">
                    <td className="p-3 text-gray-800 font-medium max-w-[180px] truncate" title={m.name}>{m.name}</td>
                    <td className="p-3 text-gray-500">{m.type}</td>
                    <td className="p-3 text-gray-500 text-xs max-w-[120px] truncate">{m.source_org}</td>
                    <td className="p-3 text-gray-500 text-xs">{m.collector}</td>
                    <td className="p-3">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${m.confidentiality_level === "high" || m.confidentiality_level === "top_secret" ? "bg-red-100 text-red-600" : "bg-gray-100 text-gray-500"}`}>
                        {CONF_LABELS[m.confidentiality_level] || m.confidentiality_level}
                      </span>
                    </td>
                    <td className="p-3 text-gray-400 font-mono text-xs">{m.file_hash ? m.file_hash.slice(0, 8) + "..." : "-"}</td>
                    <td className="p-3">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${statusColor(m.processing_status)}`}>
                        {statusLabel(m.processing_status)}
                      </span>
                    </td>
                    <td className="p-3 text-gray-400 text-xs">{m.created_at?.slice(0, 19) || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
