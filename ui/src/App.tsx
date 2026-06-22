import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { CaseList } from "./pages/CaseList";
import { CaseDetail } from "./pages/CaseDetail";
import { MaterialUpload } from "./pages/MaterialUpload";
import { EvidenceViewer } from "./pages/EvidenceViewer";
import { Analysis } from "./pages/Analysis";
import { HumanReview } from "./pages/HumanReview";
import { ReportView } from "./pages/ReportView";

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen">
        <Sidebar />
        <main className="flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<CaseList />} />
            <Route path="/case/:caseId" element={<CaseDetail />} />
            <Route path="/materials" element={<MaterialUpload />} />
            <Route path="/evidence" element={<EvidenceViewer />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/review" element={<HumanReview />} />
            <Route path="/report" element={<ReportView />} />
            <Route path="/report/:reportId" element={<ReportView />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
