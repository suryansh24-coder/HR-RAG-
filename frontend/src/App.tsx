import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppProvider, useApp } from "./state/AppContext";
import { AppShell } from "./components/AppShell";
import { ErrorState, LoadingPanel } from "./components/Feedback";
import { ChatPage } from "./pages/ChatPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { DashboardPage } from "./pages/DashboardPage";

/** Exported for tests: renders the API-availability gate and, when online, the routes. */
export function OfflineGate() {
  const { offline, loading } = useApp();

  // Only block the app when the API is genuinely unreachable; the Dashboard and
  // Documents screens have their own per-screen error states for partial failure.
  if (loading) return <LoadingPanel label="Connecting to the HR Nexus API" />;
  if (offline) {
    return (
      <div className="mx-auto max-w-2xl px-5 py-20">
        <ErrorState
          title="Cannot reach the API"
          message="The backend at /api is not responding. Start it with `uvicorn app.main:app --app-dir backend`, then reload."
        />
      </div>
    );
  }
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<ChatPage />} />
        <Route path="chat" element={<Navigate to="/" replace />} />
        <Route path="chat/:conversationId" element={<ChatPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <OfflineGate />
      </AppProvider>
    </BrowserRouter>
  );
}
