/** FastAPI 后端 API 客户端。开发时通过 Vite proxy 转发到 localhost:8000。 */

const BASE = "/api";

export interface AnalysisResult {
  query: string;
  retrieved_chunks: { chunk_id: string; source_type: string; effective_date: string; content_preview: string; distance: number }[];
  analysis: string;
}

export interface CaseItem {
  case_id: string;
  case_name: string;
  case_number: string;
  case_type: string;
  charge?: string;
  decision_type?: string;
  created_at: string;
}

export async function analyzeEvidence(caseId: string, query: string, context: string = ""): Promise<AnalysisResult> {
  const res = await fetch(`${BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId, query, case_context: context }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function listCases(): Promise<CaseItem[]> {
  const res = await fetch(`${BASE}/cases`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getCase(caseId: string): Promise<CaseItem & { fact?: string; evidence_list?: any[] }> {
  const res = await fetch(`${BASE}/cases/${caseId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
