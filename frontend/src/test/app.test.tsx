import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OfflineGate } from "../App";
import { AppProvider } from "../state/AppContext";
import { AppShell } from "../components/AppShell";
import { ChatPage } from "../pages/ChatPage";
import { DocumentsPage } from "../pages/DocumentsPage";
import { SourceCard } from "../components/SourceList";
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

/** Installs a stub `fetch` that answers the API routes the app boots with. */
function installFetch(overrides: Record<string, () => Response> = {}) {
  vi.stubGlobal("fetch", vi.fn(makeHandler(overrides)));
}

/** Builds the route handler without installing it, so a test can wrap it. */
function makeHandler(overrides: Record<string, () => Response> = {}) {
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
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
}

/** Same behaviour as the `ChatAlias` route in App.tsx. */
function ChatAlias() {
  const { search } = useLocation();
  return <Navigate to={`/${search}`} replace />;
}

function renderApp(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<ChatPage />} />
            {/* Mirrors App.tsx: `/chat` is an alias that keeps the search string,
                which is how the dashboard hands a question to the composer. */}
            <Route path="/chat" element={<ChatAlias />} />
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
  document.documentElement.removeAttribute("data-theme");
  window.localStorage.clear();
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

  it("switches the whole palette when the theme toggle is used", async () => {
    installFetch();
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Connected");

    const toLight = screen.getByRole("button", { name: /switch to light theme/i });
    await user.click(toLight);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument();

    // The preference must survive a reload of the tab.
    expect(window.localStorage.getItem("hr-nexus.theme")).toBe("light");
  });
});

describe("conversation history", () => {
  it("lists persisted conversations and reopens one", async () => {
    installFetch({
      "/api/conversations": () =>
        routeFetch({
          conversations: [
            { id: "c1", title: "Annual leave", message_count: 4, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:05:00Z" },
            { id: "c2", title: "Expense limits", message_count: 2, created_at: "2026-01-02T00:00:00Z", updated_at: "2026-01-02T00:01:00Z" },
          ],
          total: 2,
        }),
      "/api/conversations/c1": () =>
        routeFetch({
          id: "c1",
          title: "Annual leave",
          message_count: 2,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:05:00Z",
          messages: [
            { id: "m1", role: "user", content: "How many days do I get?", sources: null, no_context: false, created_at: "2026-01-01T00:00:00Z" },
            { id: "m2", role: "assistant", content: "25 days per year.", sources: [], no_context: false, created_at: "2026-01-01T00:00:05Z" },
          ],
        }),
    });

    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Connected");

    await user.click(screen.getByRole("button", { name: "History" }));
    expect(await screen.findByText("Annual leave")).toBeInTheDocument();
    expect(screen.getByText("Expense limits")).toBeInTheDocument();

    await user.click(screen.getByText("Annual leave"));
    expect(await screen.findByText("25 days per year.")).toBeInTheDocument();
  });

  it("keeps one conversation across turns by reusing the streamed id", async () => {
    const sent: { question: string; conversation_id: string | null }[] = [];
    const base = makeHandler();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (!url.includes("/api/chat/stream")) return base(input, init);

        const body = JSON.parse(String(init?.body ?? "{}")) as {
          question: string;
          conversation_id: string | null;
        };
        sent.push({ question: body.question, conversation_id: body.conversation_id });
        const id = body.conversation_id ?? "generated-1";
        const sse = [
          `event: start\ndata: ${JSON.stringify({ conversation_id: id, question: body.question })}\n\n`,
          `event: sources\ndata: ${JSON.stringify({ sources: [] })}\n\n`,
          `event: complete\ndata: ${JSON.stringify({ answer: "Grounded answer.", sources: [], no_context: false })}\n\n`,
        ].join("");
        return new Response(sse, { status: 200, headers: { "Content-Type": "text/event-stream" } });
      }),
    );

    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Extractive mode");

    const field = screen.getByLabelText(/your question/i);
    await user.type(field, "First question{enter}");
    expect(await screen.findByText("Grounded answer.")).toBeInTheDocument();

    await user.type(field, "Second question{enter}");
    await waitFor(() => expect(sent).toHaveLength(2));

    expect(sent[0]?.conversation_id).toBeNull();
    // The id handed back by the first stream must be reused, otherwise every
    // turn would start a brand new conversation and lose the history.
    expect(sent[1]?.conversation_id).toBe("generated-1");
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

  it("renders the follow-ups the stream returned for the sources it used", async () => {
    const base = makeHandler();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (!url.includes("/api/chat/stream")) return base(input, init);
        const sse = [
          `event: start\ndata: ${JSON.stringify({ conversation_id: "c-1" })}\n\n`,
          `event: complete\ndata: ${JSON.stringify({
            answer: "Grounded answer.",
            sources: [],
            no_context: false,
            suggestions: ["What does the policy say about sick leave?"],
          })}\n\n`,
        ].join("");
        return new Response(sse, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Extractive mode");

    await user.type(screen.getByLabelText(/your question/i), "How much annual leave?{enter}");
    expect(await screen.findByText("Grounded answer.")).toBeInTheDocument();
    // Grounded from the real retrieved sources, not a static list.
    expect(
      await screen.findByRole("button", { name: /what does the policy say about sick leave/i }),
    ).toBeInTheDocument();
  });

  it("asks the question handed over from the dashboard (?q=) exactly once", async () => {
    const sent: string[] = [];
    const base = makeHandler();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (!url.includes("/api/chat/stream")) return base(input, init);
        const body = JSON.parse(String(init?.body ?? "{}")) as { question: string };
        sent.push(body.question);
        const sse = [
          `event: start\ndata: ${JSON.stringify({ conversation_id: "c-9" })}\n\n`,
          `event: complete\ndata: ${JSON.stringify({ answer: "Leave is 21 days.", sources: [], no_context: false })}\n\n`,
        ].join("");
        return new Response(sse, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    renderApp("/chat?q=How%20many%20annual%20leave%20days%3F");
    // Re-queried on every poll rather than holding the node found by findByText:
    // the answer text is patched in while React is still committing the stream,
    // so a captured node can be replaced by a later render.
    await waitFor(() => expect(screen.getByText("Leave is 21 days.")).toBeInTheDocument());
    expect(sent).toEqual(["How many annual leave days?"]);

    // The parameter is cleared, so re-rendering cannot ask the same question twice.
    await waitFor(() => expect(screen.queryByLabelText(/your question/i)).toBeInTheDocument());
    expect(sent).toHaveLength(1);
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

  it("replaces the write controls with the token gate on a protected deployment", async () => {
    let verified = false;
    const base = makeHandler({
      "/api/auth/status": () =>
        routeFetch({ auth_required: true, auth_configured: true, verified }),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/api/auth/status")) {
          // A correct `Authorization` header is what flips `verified`, exactly
          // as the server would answer.
          const header = new Headers(init?.headers).get("Authorization");
          verified = header === "Bearer s3cret";
          return routeFetch({ auth_required: true, auth_configured: true, verified });
        }
        return base(input, init);
      }),
    );

    const user = userEvent.setup();
    renderApp("/documents");

    expect(await screen.findByText(/management token required/i)).toBeInTheDocument();
    // Uploading is a write: the control must not be reachable while locked.
    expect(screen.queryByRole("button", { name: /^upload$/i })).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/^token$/i), "s3cret");
    await user.click(screen.getByRole("button", { name: /unlock/i }));

    expect(await screen.findByRole("button", { name: /^upload$/i })).toBeInTheDocument();
  });
});

describe("SourceCard", () => {
  const source = {
    chunk_id: "chunk-1",
    document_id: "doc-1",
    filename: "leave_policy.pdf",
    page: 1,
    chunk_index: 0,
    document_type: "pdf",
    score: 0.83,
    citation: "leave_policy.pdf · page 1",
    snippet: "Every full-time employee receives 18 days of paid annual leave.",
  };

  /** Stubs the object-URL and popup APIs jsdom does not implement. */
  function stubBlobAndPopup() {
    const created: string[] = [];
    const revoked: string[] = [];
    vi.stubGlobal("URL", Object.assign(URL, {
      createObjectURL: vi.fn(() => {
        const url = `blob:http://test/${created.length + 1}`;
        created.push(url);
        return url;
      }),
      revokeObjectURL: vi.fn((url: string) => {
        revoked.push(url);
      }),
    }));
    const open = vi.fn((_url: string, _target?: string, _features?: string) => ({
      closed: false,
      focus: vi.fn(),
    }));
    vi.stubGlobal("open", open);
    return { created, revoked, open };
  }

  it("fetches the file with the management token instead of navigating to it", async () => {
    const { open } = stubBlobAndPopup();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("pdf-bytes", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    setAuthToken("s3cret");

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <SourceCard source={source} index={0} />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: /leave_policy\.pdf/ }));
    await user.click(screen.getByRole("button", { name: /open the source file/i }));

    await waitFor(() => expect(open).toHaveBeenCalledTimes(1));
    const [url, target, features] = open.mock.calls[0]!;
    expect(url).toMatch(/^blob:/);
    expect(target).toBe("_blank");
    expect(features).toContain("noopener");

    // The whole point of the fetch: a navigation could not carry the header.
    const [requestUrl, init] = fetchMock.mock.calls[0]!;
    expect(requestUrl).toContain("/api/documents/doc-1/file");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer s3cret");
  });

  it("explains the failure instead of opening an empty tab when the fetch fails", async () => {
    const { open } = stubBlobAndPopup();
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("nope", { status: 401 })));
    setAuthToken("wrong");

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <SourceCard source={source} index={0} />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: /leave_policy\.pdf/ }));
    await user.click(screen.getByRole("button", { name: /open the source file/i }));

    expect(await screen.findByText(/401/)).toBeInTheDocument();
    expect(open).not.toHaveBeenCalled();
  });

  it("releases the previous object URL when the same source is opened twice", async () => {
    const { revoked, open } = stubBlobAndPopup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("pdf-bytes", { status: 200 })),
    );
    setAuthToken(null);

    // The release is deliberately deferred, so capture the scheduled callbacks
    // and run them by hand instead of faking timers under userEvent.
    const realSetTimeout = window.setTimeout.bind(window);
    const scheduled: Array<() => void> = [];
    const spy = vi.spyOn(window, "setTimeout").mockImplementation(((
      callback: TimerHandler,
      delay?: number,
      ...args: unknown[]
    ) => {
      if (typeof callback === "function" && delay === 30_000) scheduled.push(callback as () => void);
      return realSetTimeout(callback, delay, ...args);
    }) as typeof window.setTimeout);

    try {
      const { unmount } = render(
        <MemoryRouter>
          <SourceCard source={source} index={0} />
        </MemoryRouter>,
      );
      const user = userEvent.setup();

      await user.click(await screen.findByRole("button", { name: /leave_policy\.pdf/ }));
      const trigger = screen.getByRole("button", { name: /open the source file/i });
      await user.click(trigger);
      await waitFor(() => expect(open).toHaveBeenCalledTimes(1));
      await user.click(trigger);
      expect(open).toHaveBeenCalledTimes(2);

      // The first URL is released rather than pinning the file for the session.
      expect(scheduled).toHaveLength(1);
      scheduled[0]!();
      expect(revoked).toEqual(["blob:http://test/1"]);

      unmount();
      expect(scheduled).toHaveLength(2);
      scheduled[1]!();
      expect(revoked).toEqual(["blob:http://test/1", "blob:http://test/2"]);
    } finally {
      spy.mockRestore();
    }
  });
});
