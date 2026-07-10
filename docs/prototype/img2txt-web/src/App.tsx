import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import LandingPage from "./routes/LandingPage";
import UploadPage from "./routes/UploadPage";
import JobPage from "./routes/JobPage";
import ResultPage from "./routes/ResultPage";
import AppHeader from "./components/AppHeader";

function AppLayout() {
  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<AppLayout />}>
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/jobs/:jobId" element={<JobPage />} />
        <Route path="/jobs/:jobId/result" element={<ResultPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
