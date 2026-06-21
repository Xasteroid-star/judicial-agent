/** 卷宗接入模块 — architecture.md §5.1 */
import { useState } from "react";

const MATERIAL_TYPES = [
  "文本文书", "扫描件", "图片", "视频", "音频", "表格", "聊天记录", "电子数据检查材料",
];

interface UploadedMaterial {
  id: string;
  name: string;
  type: string;
  source_org: string;
  collector: string;
  confidentiality: string;
  size: string;
  hash: string;
  status: string;
  time: string;
}

export function MaterialUpload() {
  const [materials] = useState<UploadedMaterial[]>([
    {
      id: "M-001", name: "受案登记表.pdf", type: "文本文书",
      source_org: "上海市公安局浦东分局", collector: "侦查员张某",
      confidentiality: "中", size: "245 KB", hash: "a3f2...8c1d",
      status: "已登记", time: "2024-08-06 14:30",
    },
    {
      id: "M-002", name: "现场勘查照片.zip", type: "图片",
      source_org: "上海市公安局浦东分局", collector: "技术科",
      confidentiality: "中", size: "12.3 MB", hash: "b7e1...4f2a",
      status: "已登记", time: "2024-08-06 15:00",
    },
    {
      id: "M-003", name: "李某询问笔录.docx", type: "文本文书",
      source_org: "上海市公安局浦东分局", collector: "侦查员王某",
      confidentiality: "中", size: "56 KB", hash: "c2d4...9a7b",
      status: "已登记", time: "2024-08-07 09:15",
    },
    {
      id: "M-004", name: "讯问录音.mp3", type: "音频",
      source_org: "上海市公安局浦东分局", collector: "侦查员张某",
      confidentiality: "高", size: "45.8 MB", hash: "d8f3...2e6c",
      status: "待处理", time: "2024-08-07 11:00",
    },
    {
      id: "M-005", name: "银行流水.xlsx", type: "表格",
      source_org: "中国工商银行", collector: "侦查员李某",
      confidentiality: "高", size: "1.2 MB", hash: "e4a6...5b1f",
      status: "待处理", time: "2024-08-08 10:45",
    },
  ]);

  const statusColor = (s: string) =>
    s === "已登记" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700";

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-800">卷宗接入</h2>
        <button className="px-4 py-2 bg-[var(--color-accent)] text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          + 上传材料
        </button>
      </div>

      {/* 上传区域 */}
      <div className="bg-white rounded-lg border border-dashed p-8 text-center mb-6 hover:border-[var(--color-accent)] transition-colors cursor-pointer">
        <p className="text-gray-400 text-sm">
          拖放文件到此处，或点击上方按钮选择文件
        </p>
        <p className="text-gray-300 text-xs mt-1">
          支持：PDF、DOCX、XLSX、JPG、PNG、MP3、MP4、ZIP
        </p>
      </div>

      {/* 材料列表 */}
      <div className="bg-white rounded-lg border">
        <div className="p-4 border-b">
          <h3 className="font-semibold text-gray-700">
            已登记材料 ({materials.length})
          </h3>
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-400 border-b">
                <th className="p-3 font-medium">材料名称</th>
                <th className="p-3 font-medium">类型</th>
                <th className="p-3 font-medium">来源</th>
                <th className="p-3 font-medium">密级</th>
                <th className="p-3 font-medium">大小</th>
                <th className="p-3 font-medium">哈希</th>
                <th className="p-3 font-medium">状态</th>
                <th className="p-3 font-medium">登记时间</th>
              </tr>
            </thead>
            <tbody>
              {materials.map((m) => (
                <tr key={m.id} className="border-b hover:bg-gray-50">
                  <td className="p-3 text-gray-800 font-medium">{m.name}</td>
                  <td className="p-3 text-gray-500">{m.type}</td>
                  <td className="p-3 text-gray-500 text-xs">{m.source_org}</td>
                  <td className="p-3">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      m.confidentiality === "高" ? "bg-red-100 text-red-600" : "bg-gray-100 text-gray-500"
                    }`}>{m.confidentiality}</span>
                  </td>
                  <td className="p-3 text-gray-400">{m.size}</td>
                  <td className="p-3 text-gray-400 font-mono text-xs">{m.hash}</td>
                  <td className="p-3">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${statusColor(m.status)}`}>
                      {m.status}
                    </span>
                  </td>
                  <td className="p-3 text-gray-400 text-xs">{m.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
