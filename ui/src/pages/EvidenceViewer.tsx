/** 证据片段查看模块 — architecture.md §5.2-5.3 */
import { useEffect, useState } from "react";

interface EvidenceChunk {
  chunk_id: string;
  case_id: string;
  modality: string;
  content_text: string;
  extracted_elements: Record<string, string>;
  source_pointer: Record<string, any>;
  confidence: number;
  model_version: string;
}

const MODALITY_ICONS: Record<string, string> = {
  text: "📄", image: "🖼️", audio: "🎵", video: "🎬", table: "📊",
};

export function EvidenceViewer() {
  const [chunks, setChunks] = useState<EvidenceChunk[]>([]);
  const [selected, setSelected] = useState<EvidenceChunk | null>(null);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/evidence-chunks")
      .then(r => r.json())
      .then(data => setChunks(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = chunks.filter(
    (c) =>
      !filter ||
      c.content_text?.includes(filter) ||
      c.modality?.includes(filter) ||
      Object.values(c.extracted_elements || {}).some((v) => String(v).includes(filter))
  );

  return (
    <div>
      <h2 className="text-xl font-bold text-gray-800 mb-6">
        证据片段查看
        {!loading && <span className="text-sm font-normal text-gray-400 ml-2">({chunks.length} 条)</span>}
      </h2>

      {loading ? (
        <div className="text-center text-gray-400 py-12">加载中...</div>
      ) : error ? (
        <div className="text-center text-red-400 py-12">加载失败: {error}</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 片段列表 */}
          <div className="bg-white rounded-lg border">
            <div className="p-4 border-b">
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none"
                placeholder="搜索证据片段..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
            <div className="divide-y max-h-[600px] overflow-auto">
              {filtered.map((chunk) => (
                <div
                  key={chunk.chunk_id}
                  onClick={() => setSelected(chunk)}
                  className={`p-4 cursor-pointer transition-colors hover:bg-gray-50 ${
                    selected?.chunk_id === chunk.chunk_id ? "bg-blue-50 border-l-2 border-[var(--color-accent)]" : ""
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span>{MODALITY_ICONS[chunk.modality] || "📋"}</span>
                    <span className="text-xs text-gray-400">{chunk.chunk_id?.slice(0, 12)}...</span>
                    <span className={`text-xs px-1.5 rounded ${
                      (chunk.confidence ?? 0) >= 0.85 ? "bg-green-100 text-green-600" :
                      (chunk.confidence ?? 0) >= 0.70 ? "bg-yellow-100 text-yellow-600" : "bg-red-100 text-red-600"
                    }`}>
                      {Math.round((chunk.confidence ?? 0) * 100)}%
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 line-clamp-2">{chunk.content_text}</p>
                  {chunk.extracted_elements && Object.keys(chunk.extracted_elements).length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {Object.entries(chunk.extracted_elements).slice(0, 3).map(([k, v]) => (
                        <span key={k} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                          {k}: {String(v).slice(0, 15)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* 详情 */}
          {selected ? (
            <div className="bg-white rounded-lg border p-6 space-y-4">
              <div>
                <span className="text-xs text-gray-400">{selected.chunk_id}</span>
                <h3 className="font-semibold text-gray-800 mt-1">
                  {MODALITY_ICONS[selected.modality] || "📋"} {selected.modality?.toUpperCase()} 片段
                </h3>
              </div>

              <div>
                <h4 className="text-sm font-medium text-gray-500 mb-1">内容</h4>
                <p className="text-sm text-gray-800 leading-relaxed bg-gray-50 p-3 rounded">
                  {selected.content_text}
                </p>
              </div>

              <div>
                <h4 className="text-sm font-medium text-gray-500 mb-1">抽取要素</h4>
                <div className="grid grid-cols-2 gap-2">
                  {selected.extracted_elements && Object.keys(selected.extracted_elements).length > 0 ? (
                    Object.entries(selected.extracted_elements).map(([k, v]) => (
                      <div key={k} className="flex gap-2 text-sm">
                        <span className="text-gray-400">{k}:</span>
                        <span className="text-gray-700">{String(v)}</span>
                      </div>
                    ))
                  ) : (
                    <span className="text-gray-400 text-xs">暂无要素</span>
                  )}
                </div>
              </div>

              <div>
                <h4 className="text-sm font-medium text-gray-500 mb-1">溯源指针</h4>
                <div className="text-xs text-gray-400 space-y-1">
                  <p>材料ID: {selected.source_pointer?.material_id || "-"}</p>
                  {selected.source_pointer?.page && <p>页码: 第{selected.source_pointer.page}页</p>}
                  {selected.source_pointer?.paragraph !== undefined && <p>段落: 第{selected.source_pointer.paragraph}段</p>}
                </div>
              </div>

              <div className="flex items-center justify-between pt-4 border-t">
                <span className="text-xs text-gray-400">模型版本: {selected.model_version || "-"}</span>
                <span className={`text-sm font-medium ${
                  (selected.confidence ?? 0) >= 0.85 ? "text-green-600" :
                  (selected.confidence ?? 0) >= 0.70 ? "text-yellow-600" : "text-red-600"
                }`}>
                  置信度: {Math.round((selected.confidence ?? 0) * 100)}%
                </span>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-lg border p-12 text-center text-gray-300">
              选择一个证据片段查看详情
            </div>
          )}
        </div>
      )}
    </div>
  );
}
