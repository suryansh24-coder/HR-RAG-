/**
 * Response types for the HR Nexus API.
 *
 * Every field here was read off the live OpenAPI schema
 * (`python scripts/dump_frontend_contract.py`) rather than assumed. An earlier
 * draft of this file invented `chunks_pending`, `cosine_similarity`,
 * `latency_ms` and `snippet`, none of which the API returns; the contract test
 * in `src/test/api-contract.test.ts` now pins these names so that mistake
 * cannot come back silently.
 */

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface MetaFeatures {
  streaming: boolean;
  auth_required: boolean;
  debug: boolean;
  database: string;
  qdrant_mode: string;
  [key: string]: unknown;
}

export interface MetaResponse {
  detail: string;
  version: string;
  environment: string;
  api_prefix: string;
  features: MetaFeatures;
}

export interface HealthComponent {
  status: "ok" | "degraded" | "error" | string;
  detail: string | null;
  latency_ms: number | null;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "error" | string;
  app: string;
  version: string;
  environment: string;
  components: Record<string, HealthComponent>;
}

export interface DocumentOut {
  id: string;
  filename: string;
  document_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  chunk_count: number;
  page_count: number;
  processing_time_ms: number | null;
  uploaded_at: string;
  indexed_at: string | null;
}

export interface DocumentListResponse {
  documents: DocumentOut[];
  total: number;
  indexed: number;
  failed: number;
  processing: number;
}

export interface UploadResponse {
  document: DocumentOut;
  message: string;
}

export interface ReindexResponse {
  document: DocumentOut;
  message: string;
}

/** `DocumentDetail` extends `DocumentOut` in the API, so it is flat here too. */
export interface DocumentDetail extends DocumentOut {
  chunks: DocumentChunkOut[];
  collection_chunks: number;
}

export interface DocumentChunkOut {
  chunk_index: number;
  page: number;
  text: string;
  citation: string;
}

export interface UploadLimits {
  max_upload_size_mb: number;
  max_upload_size_bytes: number;
  allowed_extensions: string[];
  allowed_content_types: string[];
  auth_required: boolean;
}

export interface ChatConfig {
  no_context_response: string;
  max_question_chars: number;
  history_turns: number;
  streaming: boolean;
}

export interface SourceOut {
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number;
  chunk_index: number;
  document_type: string;
  score: number;
  citation: string;
  snippet: string;
}

export interface ChatResponse {
  answer: string;
  sources: SourceOut[];
  suggestions: string[];
  context_used: boolean;
  no_context: boolean;
  /** Nullable: the API does not create a conversation for ungrounded answers. */
  conversation_id: string | null;
  message_id: string | null;
  retrieval_hits: number;
  trace: Record<string, unknown>;
  total_latency_ms: number | null;
}

export interface MessageOut {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | string;
  content: string;
  sources: SourceOut[] | null;
  no_context: boolean;
  created_at: string;
  latency_ms: number | null;
}

export interface ConversationOut {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string | null;
}

export interface ConversationListResponse {
  conversations: ConversationOut[];
  total: number;
}

export interface ConversationDetail {
  conversation: ConversationOut;
  messages: MessageOut[];
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number;
  chunk_index: number;
  document_type: string;
  score: number;
  citation: string;
  text: string;
}

export interface SearchResponse {
  question: string;
  hits: SearchHit[];
  trace: Record<string, unknown>;
}

export interface CollectionInfo {
  name: string;
  exists: boolean;
  status: string;
  points_count: number;
  vectors_count: number;
  indexed_vectors_count: number;
  dimension: number | null;
  distance: string | null;
}

export interface RagConfigOut {
  embedding_model: string;
  embedding_dimension: number | null;
  llm_provider: string;
  llm_model: string;
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  score_threshold: number;
  max_chunks_per_document: number;
  max_context_chunks: number;
  history_turns: number;
  qdrant_mode: string;
  qdrant_collection: string;
  allowed_extensions: string[];
  max_upload_size_mb: number;
}

export interface RagMetrics {
  queries_total: number;
  grounded_answers: number;
  no_context_answers: number;
  errors_total: number;
  grounded_ratio: number | null;
  avg_chunks_retrieved: number | null;
  avg_retrieval_ms: number | null;
  p95_retrieval_ms: number | null;
  avg_generation_ms: number | null;
  avg_total_ms: number | null;
  p95_total_ms: number | null;
  avg_top_score: number | null;
  uptime_seconds: number;
  [key: string]: unknown;
}

export interface RagStatsResponse {
  documents_total: number;
  documents_indexed: number;
  documents_processing: number;
  documents_failed: number;
  total_chunks: number;
  chunks_indexed: number;
  qdrant_status: string;
  collection: CollectionInfo;
  last_indexed_at: string | null;
  queries_total: number;
  queries_grounded: number;
  queries_no_context: number;
  conversations_total: number;
  messages_total: number;
  last_query_at: string | null;
  metrics: RagMetrics;
  config: RagConfigOut;
  debug_mode: boolean;
}

export interface QueryLogOut {
  id: string;
  question_preview: string;
  grounded: boolean;
  chunks_retrieved: number;
  top_score: number | null;
  total_latency_ms: number | null;
  created_at: string;
}

export interface QueryLogListResponse {
  entries: QueryLogOut[];
  total: number;
}

export interface AuthStatusResponse {
  auth_required: boolean;
  auth_configured: boolean;
  verified: boolean;
}

/**
 * Stages emitted by `POST /api/chat/stream`.
 *
 * `pipeline.Stage` is the literal `retrieving | sources | generating | complete`;
 * the route adds `start` before it and `error` on failure, so the stream is
 * `start → retrieving → sources → generating → complete | error`.
 */
export type StreamStage = "start" | "retrieving" | "sources" | "generating" | "complete" | "error";

export interface StreamEvent {
  stage: StreamStage;
  message: string;
  data: Record<string, unknown>;
}
