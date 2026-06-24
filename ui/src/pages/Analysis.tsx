/** 证据链分析 — 先从 DB 加载本案证据，再 RAG 补充，图谱动态生成 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EvidenceGraph } from "../components/EvidenceGraph";

interface CaseOption {
  case_id: string;
  case_name: string;
  charge?: string;
  fact?: string;
}

export function Analysis() {
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [selectedCase, setSelectedCase] = useState<CaseOption | null>(null);
  const [query, setQuery] = useState("");
  const [caseContext, setCaseContext] = useState("");
  const [mode, setMode] = useState<"fast" | "llm">("fast");
  const [stream, setStream] = useState(false);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState<number>(0);
  const [result, setResult] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<any>(null);
  const [chunks, setChunks] = useState<any[]>([]);
  const [localEvidence, setLocalEvidence] = useState<any[]>([]);
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] } | null>(null);
  // 流式进度
  const [phases, setPhases] = useState<{ name: string; done: boolean }[]>([]);
  const [observeLog, setObserveLog] = useState<any[]>([]);
  const [searchParams] = useSearchParams();
  const urlCaseId = searchParams.get("caseId") || "";

  // 加载案件列表
  useEffect(() => {
    fetch("/api/cases")
      .then((r) => r.json())
      .then((list) => {
        setCases(list);
        // URL 带有 caseId 时自动选中
        if (urlCaseId) {
          const found = list.find((c: CaseOption) => c.case_id === urlCaseId);
          if (found) setSelectedCase(found);
        }
      })
      .catch(() => {});
  }, [urlCaseId]);

  // 选中案件后加载本案证据
  useEffect(() => {
    if (!selectedCase) return;
    fetch(`/api/cases/${selectedCase.case_id}`)
      .then((r) => r.json())
      .then((data) => {
        setCaseContext(data.fact || data.case_name || "");
        // 本案证据优先展示
        const evList = (data.evidence_list || []).map((ev: any, i: number) => ({
          chunk_id: `local-${i}`,
          content_preview: `[${ev.type}] ${ev.name}`,
          source_type: "case",
          evidence_type: ev.type,
          distance: 0.05, // 本案证据距离最低
        }));
        setLocalEvidence(evList);
      })
      .catch(() => {});
  }, [selectedCase]);

  const handleAnalyze = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setResult(null);
    setConfidence(null);
    setGraphData(null);
    setPhases([]);
    const t0 = performance.now();

    if (stream) {
      // ── SSE 流式 ──
      try {
        const res = await fetch("/api/analyze/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ case_id: selectedCase?.case_id || "", query, case_context: caseContext || query, mode }),
        });
        const reader = res.body?.getReader();
        if (!reader) throw new Error("无法读取流");
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() || "";
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const evt = JSON.parse(line.slice(6));
              if (evt.phase === "complete") {
                const data = evt.result;
                setElapsed(Math.round((performance.now() - t0) / 10) / 100);
                setResult(data.report?.markdown || JSON.stringify(data, null, 2));
                setConfidence(data.confidence || null);
                setObserveLog(data.observe || []);
                if (data.graph?.nodes?.length) setGraphData({ nodes: data.graph.nodes, edges: data.graph.edges || [] });
              } else {
                setPhases(prev => [...prev, { name: evt.phase, done: true }]);
              }
            }
          }
        }
      } catch (e: any) {
        setResult(`流式错误: ${e.message}`);
      } finally {
        setLoading(false);
      }
      return;
    }

    // ── 普通模式 ──
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: selectedCase?.case_id || "", query, case_context: caseContext || query, mode }),
      });
      const data = await res.json();
      setElapsed(Math.round((performance.now() - t0) / 10) / 100);
      setResult(data.report?.markdown || data.analysis || JSON.stringify(data, null, 2));
      setConfidence(data.confidence || null);
      // 图谱数据
      if (data.graph?.nodes?.length) {
        setGraphData({ nodes: data.graph.nodes, edges: data.graph.edges || [] });
      } else {
        setGraphData(null);
      }
      // 本案证据优先 + RAG 结果补充
      const ragChunks = [
        ...(data.retrieved_statutes || []).map((c: any) => ({ ...c, source_type: "statute" })),
        ...(data.retrieved_chunks || []).map((c: any) => ({ ...c, source_type: "case" })),
      ];
      // 去重
      const seen = new Set(localEvidence.map((e) => e.content_preview));
      const filtered = ragChunks.filter((c: any) => !seen.has(c.content_preview));
      setChunks([...localEvidence, ...filtered]);
    } catch (e: any) {
      setResult(`错误: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-xl font-bold text-gray-800 mb-6">证据链分析</h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 输入区 */}
        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-semibold text-gray-700 mb-4">分析参数</h3>

          {/* 案件选择器 */}
          <label className="block text-sm text-gray-500 mb-1">选择案件</label>
          <select
            className="w-full border rounded-lg p-2.5 text-sm mb-4 focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none bg-white"
            value={selectedCase?.case_id || ""}
            onChange={(e) => {
              const c = cases.find((x) => x.case_id === e.target.value);
              setSelectedCase(c || null);
            }}
          >
            <option value="">-- 选择案件（可选）--</option>
            {cases.map((c) => (
              <option key={c.case_id} value={c.case_id}>
                {c.case_name} {c.charge ? `· ${c.charge}` : ""}
              </option>
            ))}
          </select>

          {/* 模式切换 */}
          <label className="block text-sm text-gray-500 mb-1">分析模式</label>
          <div className="flex gap-2 mb-2">
            <button
              onClick={() => setMode("fast")}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === "fast"
                  ? "bg-green-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              ⚡ 快速
            </button>
            <button
              onClick={() => setMode("llm")}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === "llm"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              🧠 深度
            </button>
          </div>
          <label className="flex items-center gap-2 text-xs text-gray-400 mb-4 cursor-pointer">
            <input type="checkbox" checked={stream} onChange={e => setStream(e.target.checked)} className="rounded" />
            流式输出（边跑边看进度）
          </label>

          <label className="block text-sm text-gray-500 mb-1">分析问题</label>
          <textarea
            className="w-full border rounded-lg p-3 text-sm mb-4 h-28 resize-none focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none"
            placeholder="例：该案证据链是否完整？能否排除非法证据？"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          <label className="block text-sm text-gray-500 mb-1">案件背景（选好案件自动填充）</label>
          <textarea
            className="w-full border rounded-lg p-3 text-sm mb-4 h-20 resize-none focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none"
            value={caseContext}
            onChange={(e) => setCaseContext(e.target.value)}
          />

          <button
            onClick={handleAnalyze}
            disabled={loading || !query.trim()}
            className="w-full py-2.5 bg-[var(--color-accent)] text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (stream ? "流式分析中..." : mode === "fast" ? "分析中..." : "DeepSeek 深度分析中...") : "开始分析"}
          </button>
        </div>

        {/* 结果区 */}
        <div className="lg:col-span-2 space-y-6">
          {/* 流式进度条 */}
          {stream && phases.length > 0 && (
            <div className="bg-white rounded-lg border p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">执行进度</h3>
              <div className="flex flex-wrap gap-1.5">
                {["卷宗解析","要素抽取","RAG检索","知识图谱","证据链分析","置信度审查","报告生成","人工复核"].map(name => {
                  const done = phases.some(p => p.name === name);
                  return (
                    <span key={name} className={`text-xs px-2 py-1 rounded-full transition-colors ${
                      done ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-300"
                    }`}>
                      {done ? "✓" : "○"} {name}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
          {/* 本案证据（优先） */}
          {localEvidence.length > 0 && (
            <div className="bg-green-50 rounded-lg border border-green-200 p-4">
              <h3 className="font-semibold text-green-800 mb-3">
                本案证据 ({localEvidence.length})
              </h3>
              <div className="space-y-2 max-h-40 overflow-auto">
                {localEvidence.map((c, i) => (
                  <div key={i} className="text-sm p-2 rounded bg-white border border-green-100">
                    <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700">本案</span>
                    <span className="text-gray-600 ml-2">{c.content_preview}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 检索结果 */}
          {chunks.length > localEvidence.length && (
            <div className="bg-white rounded-lg border p-4">
              <h3 className="font-semibold text-gray-700 mb-3">
                相关材料 ({chunks.length - localEvidence.length})
              </h3>
              <div className="space-y-2 max-h-60 overflow-auto">
                {chunks.filter((c) => !localEvidence.find((l) => l.content_preview === c.content_preview)).map((c, i) => (
                  <div key={i} className="text-sm p-2 rounded bg-gray-50 border">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${c.source_type === "statute" ? "bg-yellow-100 text-yellow-700" : "bg-blue-100 text-blue-700"}`}>
                      {c.source_type === "statute" ? "法条" : "证据"}
                    </span>
                    <span className="text-gray-400 ml-2">{c.effective_date || ""}</span>
                    <p className="text-gray-600 mt-1">{c.content_preview}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 知识图谱 */}
          {graphData && graphData.nodes.length > 0 && (
            <EvidenceGraph nodes={graphData.nodes} edges={graphData.edges} />
          )}

          {/* LLM 分析报告 */}
          {result && (
            <div className="bg-white rounded-lg border p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-gray-700">分析报告</h3>
                <div className="flex items-center gap-3">
                  {confidence && (
                    <span className={`text-xs px-2 py-1 rounded font-medium ${
                      (confidence.final ?? 0) >= 0.85 ? "bg-green-100 text-green-700" :
                      (confidence.final ?? 0) >= 0.70 ? "bg-yellow-100 text-yellow-700" :
                      "bg-red-100 text-red-700"
                    }`}>
                      置信度 {Math.round((confidence.final ?? 0) * 100)}%
                      {confidence.threshold_result ? ` · ${confidence.threshold_result === "pass" ? "通过" : confidence.threshold_result === "review" ? "需复核" : confidence.threshold_result === "uncertain" ? "存疑" : "驳回"}` : ""}
                    </span>
                  )}
                  {elapsed > 0 && (
                    <span className={`text-xs px-2 py-1 rounded ${elapsed < 2 ? "bg-green-100 text-green-600" : "bg-gray-100 text-gray-500"}`}>
                      {elapsed < 2 ? `⚡ ${elapsed}s` : `${elapsed}s`}
                    </span>
                  )}
                  <span className={`text-xs px-2 py-1 rounded ${mode === "fast" ? "bg-green-50 text-green-600" : "bg-blue-50 text-blue-600"}`}>
                    {mode === "fast" ? "规则引擎" : "DeepSeek"}
                  </span>
                </div>
              </div>
              <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap">
                {result}
              </div>

              {/* Observe 决策日志 */}
              {(observeLog.length > 0 || data?.observe?.length > 0) && (
                <div className="mt-4 pt-3 border-t">
                  <h4 className="text-xs font-medium text-gray-400 mb-2">决策链路</h4>
                  <div className="flex gap-1.5 flex-wrap">
                    {(observeLog.length > 0 ? observeLog : data.observe || []).map((o: any, i: number) => (
                      <span key={i} className={`text-xs px-2 py-0.5 rounded ${
                        o.use_llm ? "bg-blue-50 text-blue-600" : "bg-green-50 text-green-600"
                      }`}>
                        {o.agent}: {o.use_llm ? "LLM" : "规则"}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!result && !loading && (
            <div className="bg-white rounded-lg border p-12 text-center text-gray-300">
              选择案件，输入分析问题后点击「开始分析」
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
