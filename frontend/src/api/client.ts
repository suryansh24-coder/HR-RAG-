import type {
  AuthStatusResponse,
  ChatConfig,
  ChatResponse,
  ConversationDetail,
  ConversationListResponse,
  ConversationOut,
  DocumentDetail,
  DocumentListResponse,
  HealthResponse,
  MetaResponse,
  QueryLogListResponse,
  RagStatsResponse,
  ReindexResponse,
  SearchResponse,
  StreamEvent,
  UploadLimits,
  UploadResponse,
} from "./types";

/** Backend error envelope produced by `app/core/exceptions.py`. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code = "error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const API_PREFIX = "/api";

/**
 * Optional absolute origin for the API, baked in at build time.
 *
 * Empty by default, which keeps every call same-origin: the Vite dev server
 * proxies `/api` to the backend, and the bundled nginx config does the same in
 * production. Set `VITE_API_ORIGIN=https://api.example.com` only when the app and
 * the API are served from genuinely different origins — the backend's
 * `CORS_ORIGINS` must allow the app's origin in that case.
 */
const API_ORIGIN = import.meta.env.VITE_API_ORIGIN?.replace(/\/+$/, "") ?? "";

let authToken: string | null = null;

/**
 * The management token is held in memory only.
 *
 * Persisting it to localStorage would leave a credential readable by any script
 * on the page for the lifetime of the token; a page reload simply asks again.
 */
export function setAuthToken(token: string | null): void {
  authToken = token && token.trim().length > 0 ? token.trim() : null;
}

export function getAuthToken(): string | null {
  return authToken;
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const value: Record<string, string> = { ...extra };
  if (authToken) value.Authorization = `Bearer ${authToken}`;
  return value;
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail = `Request failed (${response.status})`;
  let code = "error";
  try {
    const body = await response.json();
    if (body && typeof body.detail === "string") {
      detail = body.detail;
      code = typeof body.code === "string" ? body.code : code;
    } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      // FastAPI validation errors.
      detail = body.detail[0].msg;
      code = "validation_error";
    }
  } catch {
    /* non-JSON error body (proxy, gateway) — keep the generic message */
  }
  return new ApiError(detail, response.status, code);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_ORIGIN}${API_PREFIX}${path}`, {
    ...init,
    headers: headers(init.headers as Record<string, string> | undefined),
  });
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  meta: () => request<MetaResponse>("/meta"),
  health: () => request<HealthResponse>("/health"),
  authStatus: () => request<AuthStatusResponse>("/auth/status"),
  chatConfig: () => request<ChatConfig>("/chat/config"),

  stats: () => request<RagStatsResponse>("/rag/stats"),
  recentQueries: (limit = 20) => request<QueryLogListResponse>(`/rag/queries?limit=${limit}`),

  search: (question: string, topK?: number) =>
    request<SearchResponse>("/rag/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, ...(topK ? { top_k: topK } : {}) }),
    }),

  chat: (question: string, conversationId?: string | null, includeSuggestions = false) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        conversation_id: conversationId ?? null,
        include_suggestions: includeSuggestions,
      }),
    }),

  conversations: () => request<ConversationListResponse>("/conversations"),
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    request<{ conversation: ConversationOut }>(`/conversations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),

  documents: () => request<DocumentListResponse>("/documents"),
  document: (id: string) => request<DocumentDetail>(`/documents/${id}`),
  uploadLimits: () => request<UploadLimits>("/documents/limits/file"),

  /**
   * Upload a document. `onProgress` fires as the body streams; XHR is used
   * because `fetch` still cannot report upload progress.
   */
  uploadDocument(file: File, onProgress?: (percent: number) => void): Promise<UploadResponse> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append("file", file);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_ORIGIN}${API_PREFIX}/documents/upload`);
      Object.entries(headers()).forEach(([key, value]) => xhr.setRequestHeader(key, value));

      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      });
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText) as UploadResponse);
        } else {
          let detail = `Upload failed (${xhr.status})`;
          let code = "error";
          try {
            const body = JSON.parse(xhr.responseText);
            detail = body?.detail ?? detail;
            code = body?.code ?? code;
          } catch {
            /* keep the generic message */
          }
          reject(new ApiError(detail, xhr.status, code));
        }
      });
      xhr.addEventListener("error", () => reject(new ApiError("Network error during upload", 0, "network")));
      xhr.addEventListener("abort", () => reject(new ApiError("Upload cancelled", 0, "aborted")));
      xhr.send(form);
    });
  },

  reindexDocument: (id: string) => request<ReindexResponse>(`/documents/${id}/reindex`, { method: "POST" }),

  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),

  documentDownloadUrl: (id: string) => `${API_ORIGIN}${API_PREFIX}/documents/${id}/file`,
};

/**
 * Consume `POST /api/chat/stream`.
 *
 * The backend sends Server-Sent Events where the stage is the SSE `event:` name
 * and the payload is the `data:` line, so both lines are needed to rebuild an
 * event. Errors surface as a rejected promise *and* as a final `error` event,
 * because a stream that dies mid-flight should not be silently dropped.
 */
export async function streamChat(
  question: string,
  conversationId: string | null,
  handlers: {
    onEvent: (event: StreamEvent) => void;
    signal?: AbortSignal;
  },
): Promise<void> {
  const response = await fetch(`${API_ORIGIN}${API_PREFIX}/chat/stream`, {
    method: "POST",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify({ question, conversation_id: conversationId }),
    signal: handlers.signal,
  });

  if (!response.ok) throw await toApiError(response);
  if (!response.body) throw new ApiError("Streaming is not supported by this browser", 0, "unsupported");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let stage: StreamEvent["stage"] = "start";
  let sawTerminal = false;

  const flush = (block: string) => {
    let name: string | null = null;
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    const payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    stage = (name ?? payload.stage ?? stage) as StreamEvent["stage"];
    if (stage === "complete" || stage === "error") sawTerminal = true;
    const { stage: _ignored, ...data } = payload;
    handlers.onEvent({
      stage,
      message: typeof data.message === "string" ? data.message : "",
      data,
    });
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let index = buffer.indexOf("\n\n");
      while (index !== -1) {
        const block = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        if (block.trim()) flush(block);
        index = buffer.indexOf("\n\n");
      }
    }
    if (buffer.trim()) flush(buffer);
  } finally {
    reader.releaseLock();
  }

  if (!sawTerminal) {
    throw new ApiError("The connection closed before the answer finished", 0, "stream_truncated");
  }
}
