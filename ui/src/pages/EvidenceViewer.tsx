/** 证据片段查看模块 — architecture.md §5.2-5.3 */
import { useState } from "react";

interface EvidenceChunk {
  chunk_id: string;
  modality: string;
  content_text: string;
  extracted_elements: Record<string, string>;
  source_pointer: { material_id: string; page?: number; paragraph?: number };
  confidence: number;
  model_version: string;
}

const MOCK_CHUNKS: EvidenceChunk[] = [
  {
    chunk_id: "CH-001", modality: "text",
    content_text: "2024年8月5日，犯罪嫌疑人王某在上海市浦东新区某小区内，因琐事与被害人李某发生争执，持木棍将李某打伤。",
    extracted_elements: { "人物": "王某、李某", "时间": "2024-08-05", "地点": "上海市浦东新区", "行为": "持木棍殴打", "物品": "木棍" },
    source_pointer: { material_id: "M-003", page: 2, paragraph: 3 },
    confidence: 0.92, model_version: "v0.1",
  },
  {
    chunk_id: "CH-002", modality: "text",
    content_text: "经上海市公安局物证鉴定中心鉴定，被害人李某左前臂骨折，损伤程度为轻伤二级。鉴定人：赵某。",
    extracted_elements: { "人物": "李某", "证据名称": "司法鉴定意见书", "证明对象": "损伤程度" },
    source_pointer: { material_id: "M-006", page: 1, paragraph: 1 },
    confidence: 0.95, model_version: "v0.1",
  },
  {
    chunk_id: "CH-003", modality: "text",
    content_text: "证人张某（小区保安）陈述：当日下午3时许，看到王某从小区3号楼出来，手里拿着一根木棍，情绪激动。",
    extracted_elements: { "人物": "张某、王某", "时间": "当日下午3时", "地点": "小区3号楼", "物品": "木棍" },
    source_pointer: { material_id: "M-007", page: 1, paragraph: 2 },
    confidence: 0.78, model_version: "v0.1",
  },
  {
    chunk_id: "CH-004", modality: "text",
    content_text: "王某在讯问中辩称：案发当天遭到侦查人员长时间疲劳讯问，并受到威胁称'不交代就不让睡觉'。",
    extracted_elements: { "人物": "王某", "争议焦点": "非法取证" },
    source_pointer: { material_id: "M-004", page: 3, paragraph: 5 },
    confidence: 0.65, model_version: "v0.1",
  },
  {
    chunk_id: "CH-005", modality: "table",
    content_text: "银行交易记录：2024-08-05 15:22 李某账户→未知账户 转账5000元。备注：赔偿款。",
    extracted_elements: { "人物": "李某", "时间": "2024-08-05 15:22", "金额": "5000元", "账号": "李某账户" },
    source_pointer: { material_id: "M-005", page: 1, paragraph: 0 },
    confidence: 0.88, model_version: "v0.1",
  },
];

const MODALITY_ICONS: Record<string, string> = {
  text: "📄", image: "🖼️", audio: "🎵", video: "🎬", table: "📊",
};

export function EvidenceViewer() {
  const [selected, setSelected] = useState<EvidenceChunk | null>(null);
  const [filter, setFilter] = useState("");

  const filtered = MOCK_CHUNKS.filter(
    (c) =>
      !filter ||
      c.content_text.includes(filter) ||
      c.modality.includes(filter) ||
      Object.values(c.extracted_elements).some((v) => v.includes(filter))
  );

  return (
    <div>
      <h2 className="text-xl font-bold text-gray-800 mb-6">证据片段查看</h2>

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
                  <span>{MODALITY_ICONS[chunk.modality]}</span>
                  <span className="text-xs text-gray-400">{chunk.chunk_id}</span>
                  <span className={`text-xs px-1.5 rounded ${
                    chunk.confidence >= 0.85 ? "bg-green-100 text-green-600" :
                    chunk.confidence >= 0.70 ? "bg-yellow-100 text-yellow-600" : "bg-red-100 text-red-600"
                  }`}>
                    {Math.round(chunk.confidence * 100)}%
                  </span>
                </div>
                <p className="text-sm text-gray-700 line-clamp-2">{chunk.content_text}</p>
                {Object.keys(chunk.extracted_elements).length > 0 && (
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {Object.entries(chunk.extracted_elements).slice(0, 3).map(([k, v]) => (
                      <span key={k} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                        {k}: {v.slice(0, 15)}
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
                {MODALITY_ICONS[selected.modality]} {selected.modality.toUpperCase()} 片段
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
                {Object.entries(selected.extracted_elements).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-sm">
                    <span className="text-gray-400">{k}:</span>
                    <span className="text-gray-700">{v}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-1">溯源指针</h4>
              <div className="text-xs text-gray-400 space-y-1">
                <p>材料ID: {selected.source_pointer.material_id}</p>
                {selected.source_pointer.page && <p>页码: 第{selected.source_pointer.page}页</p>}
                {selected.source_pointer.paragraph !== undefined && <p>段落: 第{selected.source_pointer.paragraph}段</p>}
              </div>
            </div>

            <div className="flex items-center justify-between pt-4 border-t">
              <span className="text-xs text-gray-400">模型版本: {selected.model_version}</span>
              <span className={`text-sm font-medium ${
                selected.confidence >= 0.85 ? "text-green-600" :
                selected.confidence >= 0.70 ? "text-yellow-600" : "text-red-600"
              }`}>
                置信度: {Math.round(selected.confidence * 100)}%
              </span>
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-lg border p-12 text-center text-gray-300">
            选择一个证据片段查看详情
          </div>
        )}
      </div>
    </div>
  );
}
