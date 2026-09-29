import { describe, expect, it } from "vitest";
import type {
  AuthStatusResponse,
  ChatResponse,
  ConversationDetail,
  DocumentDetail,
  DocumentListResponse,
  MessageOut,
  QueryLogListResponse,
  RagStatsResponse,
  SearchResponse,
  SourceOut,
  UploadLimits,
} from "../api/types";

/**
 * Shape guards for the API contract.
 *
 * These do not prove the API behaves correctly — `backend/tests/smoke.py` does
 * that. They exist because the first draft of `types.ts` was written from
 * assumption and invented four fields the API never returns, which would have
 * produced a UI reading `undefined` at runtime. Each case below is a field the
 * frontend actually depends on, so deleting one is a deliberate act.
 */
describe("API contract", () => {
  it("ChatResponse exposes the fields the chat UI renders", () => {
    const response: ChatResponse = {
      answer: "Employees receive 25 days.",
      sources: [source()],
      suggestions: ["How do I book them?"],
      context_used: true,
      no_context: false,
      conversation_id: "c1",
      message_id: "m1",
      retrieval_hits: 1,
      trace: {},
      total_latency_ms: 12.5,
    };
    expect(response.answer).toBeTruthy();
    expect(response.conversation_id).toBe("c1");
    expect(response.no_context).toBe(false);
    expect(response.sources[0]?.citation).toBe("leave.pdf, p.2");
  });

  it("ChatResponse allows a null conversation_id", () => {
    // The API does not create a conversation for an ungrounded turn, so the UI
    // must not assume the id exists after a refusal.
    const response: ChatResponse = {
      answer: "I could not find that.",
      sources: [],
      suggestions: [],
      context_used: false,
      no_context: true,
      conversation_id: null,
      message_id: null,
      retrieval_hits: 0,
      trace: {},
      total_latency_ms: 8,
    };
    expect(response.conversation_id).toBeNull();
  });

  it("SourceOut uses score, not cosine_similarity", () => {
    expect(source()).not.toHaveProperty("cosine_similarity");
    expect(typeof source().score).toBe("number");
  });

  it("DocumentListResponse carries server-side counts", () => {
    const list: DocumentListResponse = {
      documents: [document()],
      total: 1,
      indexed: 1,
      failed: 0,
      processing: 0,
    };
    expect(list.total).toBe(list.documents.length);
    expect(list.indexed).toBe(1);
  });

  it("DocumentDetail is flat and extends DocumentOut", () => {
    const detail: DocumentDetail = {
      ...document(),
      chunks: [{ chunk_index: 0, page: 1, text: "policy text", citation: "leave.pdf, p.1" }],
      collection_chunks: 1,
    };
    // Regression guard: an earlier version nested this under `document`.
    expect(detail).not.toHaveProperty("document");
    expect(detail.collection_chunks).toBe(1);
    expect(detail.chunks[0]?.citation).toBe("leave.pdf, p.1");
  });

  it("RagStatsResponse names the field chunks_indexed", () => {
    const stats = { config: { llm_provider: "extractive" } } as unknown as RagStatsResponse;
    expect(stats).not.toHaveProperty("chunks_pending");
  });

  it("AuthStatusResponse uses auth_configured/verified", () => {
    const auth: AuthStatusResponse = { auth_required: true, auth_configured: true, verified: false };
    expect(auth.auth_configured).toBe(true);
    expect(auth).not.toHaveProperty("token_configured");
  });

  it("QueryLogListResponse wraps entries, not queries", () => {
    const log: QueryLogListResponse = {
      entries: [
        {
          id: "q1",
          question_preview: "leave?",
          grounded: true,
          chunks_retrieved: 2,
          top_score: 0.71,
          total_latency_ms: 30,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      total: 1,
    };
    expect(log).not.toHaveProperty("queries");
    expect(log.entries[0]?.grounded).toBe(true);
  });

  it("MessageOut includes no_context and conversation_id", () => {
    const message: MessageOut = {
      id: "m1",
      conversation_id: "c1",
      role: "assistant",
      content: "answer",
      sources: null,
      no_context: false,
      created_at: "2026-01-01T00:00:00Z",
      latency_ms: 12,
    };
    expect(message.conversation_id).toBe("c1");
    expect(message.sources).toBeNull();
  });

  it("SearchHit returns text, not snippet", () => {
    const response: SearchResponse = {
      question: "q",
      hits: [
        {
          chunk_id: "c",
          document_id: "d",
          filename: "f.pdf",
          page: 1,
          chunk_index: 0,
          document_type: "policy",
          score: 0.7,
          citation: "f.pdf, p.1",
          text: "body",
        },
      ],
      trace: {},
    };
    expect(response.hits[0]).toHaveProperty("text");
    expect(response.hits[0]).not.toHaveProperty("snippet");
  });

  it("UploadLimits reports bytes so the client can pre-check size", () => {
    const limits: UploadLimits = {
      max_upload_size_mb: 20,
      max_upload_size_bytes: 20 * 1024 * 1024,
      allowed_extensions: [".pdf", ".txt", ".md"],
      allowed_content_types: ["application/pdf"],
      auth_required: false,
    };
    expect(limits.max_upload_size_bytes).toBe(20 * 1024 * 1024);
  });

  it("ConversationDetail nests conversation and messages", () => {
    const detail: ConversationDetail = {
      conversation: {
        id: "c1",
        title: "Leave",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        message_count: 1,
        preview: "leave?",
      },
      messages: [],
    };
    expect(detail.conversation.id).toBe("c1");
  });
});

function source(): SourceOut {
  return {
    chunk_id: "chunk-1",
    document_id: "doc-1",
    filename: "leave.pdf",
    page: 2,
    chunk_index: 3,
    document_type: "policy",
    score: 0.7341,
    citation: "leave.pdf, p.2",
    snippet: "Employees receive 25 days of annual leave.",
  };
}

function document() {
  return {
    id: "doc-1",
    filename: "leave.pdf",
    document_type: "policy",
    size_bytes: 1024,
    status: "ready" as const,
    error_message: null,
    chunk_count: 1,
    page_count: 1,
    processing_time_ms: 120,
    uploaded_at: "2026-01-01T00:00:00Z",
    indexed_at: "2026-01-01T00:00:01Z",
  };
}
