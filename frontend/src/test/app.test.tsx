import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OfflineGate } from "../App";
import { AppProvider } from "../state/AppContext";
import { AppShell } from "../components/AppShell";
import { ChatPage } from "../pages/ChatPage";
import { DocumentsPage } from "../pages/DocumentsPage";
import { setAuthToken } from "../api/client";

const meta = {
  detail: "ok",
  version: "1.0.0",
  environment: "local",
  api_prefix: "/api",
  features: { streaming: true, auth_required: false, debug: true, database: "sqlite", qdrant_mode: "local" },
};

const stats = {
  documents_total: 2,
  documents_indexed: 2,
  documents_processing: 0,
  documents_failed: 0,
  total_chunks: 8,
  chunks_indexed: 8,
  qdrant_status: "green",
  collection: {
    name: "hr",
    exists: true,
    status: "green",
    points_count: 8,
    vectors_count: 8,
    indexed_vectors_count: 8,
    dimension: 384,
    distance: "Cosine",
  },
  last_indexed_at: "2026-01-01T00:00:00Z",
  queries_total: 4,
  queries_grounded: 3,
  queries_no_context: 1,
  conversations_total: 1,
  messages_total: 2,
  last_query_at: "2026-01-01T00:00:00Z",
  metrics: {
    queries_total: 4,
    grounded_answers: 3,
    no_context_answers: 1,
    errors_total: 0,
    grounded_ratio: 0.75,
    avg_chunks_retrieved: 2,
    avg_retrieval_ms: 4.2,
    p95_retrieval_ms: 6,
    avg_generation_ms: 3,
    avg_total_ms: 9,
    p95_total_ms: 11,
    avg_top_score: 0.71,
    uptime_seconds: 3600,
  },
  config: {
    embedding_model: "BAAI/bge-small-en-v1.5",
    embedding_dimension: 384,
    llm_provider: "extractive",
    llm_model: "",
    chunk_size: 800,
    chunk_overlap: 100,
    top_k: 4,
    score_threshold: 0.58,
    max_chunks_per_document: 2,
    max_context_chunks: 6,
    history_turns: 4,
    qdrant_mode: "local",
    qdrant_collection: "hr",
    allowed_extensions: [".pdf", ".txt", ".md"],
    max_upload_size_mb: 20,
  },
  debug_mode: false,
};

function routeFetch(body: unknown, init: { status?: number } = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(overrides: Record<string, () => Response> = {}) {
  const handler = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    const path = url.split("?")[0] ?? url;

    for (const [suffix, respond] of Object.entries(overrides)) {
      if (path.endsWith(suffix)) return respond();
    }

    if (path.endsWith("/api/meta")) return routeFetch(meta);
    if (path.endsWith("/api/rag/stats")) return routeFetch(stats);
    if (path.endsWith("/api/auth/status")) {
      return routeFetch({ auth_required: false, auth_configured: false, verified: false });
    }
    if (path.endsWith("/api/documents/limits/file")) {
      return routeFetch({
        max_upload_size_mb: 20,
        max_upload_size_bytes: 20971520,
        allowed_extensions: [".pdf", ".txt", ".md"],
        allowed_content_types: ["application/pdf"],
        auth_required: false,
      });
    }
    if (path.endsWith("/api/documents")) {
      return routeFetch({ documents: [], total: 0, indexed: 0, failed: 0, processing: 0 });
    }
    void init;
    return new Response("not found", { status: 404 });
  };
  vi.stubGlobal("fetch", vi.fn(handler));
}

function renderApp(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<ChatPage />} />
            <Route path="/chat/:conversationId" element={<ChatPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
          </Route>
        </Routes>
      </AppProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  setAuthToken(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AppShell", () => {
  it("reports a live connection once the API answers", async () => {
    installFetch();
    renderApp();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
  });

  it("navigates to the documents screen", async () => {
    installFetch();
    const user = userEvent.setup();
    renderApp();

    await screen.findByText("Connected");
    await user.click(screen.getByRole("link", { name: /documents/i }));

    expect(await screen.findByRole("heading", { name: "Documents" })).toBeInTheDocument();
  });

  it("blocks the app and explains how to fix it when the API is down", async () => {
    // Render the real <App> here rather than renderApp: the offline message is
    // produced by OfflineGate, which renderApp deliberately bypasses.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Failed to fetch")));

    render(
      <AppProvider>
        <OfflineGate />
      </AppProvider>,
    );

    expect(await screen.findByText(/cannot reach the api/i)).toBeInTheDocument();
    expect(screen.getByText(/uvicorn app\.main:app/)).toBeInTheDocument();
  });
});

describe("ChatPage", () => {
  it("shows the extractive-mode badge so the answer style is not misrepresented", async () => {
    installFetch();
    renderApp();
    expect(await screen.findByText("Extractive mode")).toBeInTheDocument();
  });

  it("offers example questions before anything is asked", async () => {
    installFetch();
    renderApp();
    expect(
      await screen.findByText("What is the annual leave entitlement?"),
    ).toBeInTheDocument();
  });

  it("does not submit an empty question", async () => {
    installFetch();
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Extractive mode");

    const send = screen.getByRole("button", { name: /ask/i });
    expect(send).toBeDisabled();

    await user.type(screen.getByLabelText(/your question/i), "   ");
    expect(send).toBeDisabled();
  });
});

describe("DocumentsPage", () => {
  it("shows the upload constraints reported by the server", async () => {
    installFetch();
    renderApp("/documents");

    expect(await screen.findByText(/Up to 20 MB each/i)).toBeInTheDocument();
  });

  it("guides the user to upload when the corpus is empty", async () => {
    installFetch();
    renderApp("/documents");

    expect(await screen.findByText("No documents yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload your first document/i })).toBeInTheDocument();
  });

  it("lists documents with their real status", async () => {
    installFetch({
      "/api/documents": () =>
        routeFetch({
          documents: [
            {
              id: "d1",
              filename: "leave_policy.pdf",
              document_type: "policy",
              size_bytes: 2048,
              status: "ready",
              error_message: null,
              chunk_count: 5,
              page_count: 3,
              processing_time_ms: 900,
              uploaded_at: "2026-01-01T00:00:00Z",
              indexed_at: "2026-01-01T00:00:01Z",
            },
            {
              id: "d2",
              filename: "expenses.docx",
              document_type: "other",
              size_bytes: 1024,
              status: "failed",
              error_message: "Unsupported file type",
              chunk_count: 0,
              page_count: 0,
              processing_time_ms: null,
              uploaded_at: "2026-01-01T00:00:00Z",
              indexed_at: null,
            },
          ],
          total: 2,
          indexed: 1,
          failed: 1,
          processing: 0,
        }),
    });

    renderApp("/documents");

    expect(await screen.findByText("leave_policy.pdf")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    // A failed document must surface the server's reason, not just "Failed".
    expect(screen.getByText("Unsupported file type")).toBeInTheDocument();
  });

  it("surfaces a real error when the documents request fails", async () => {
    installFetch({
      "/api/documents": () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
    });

    renderApp("/documents");
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
