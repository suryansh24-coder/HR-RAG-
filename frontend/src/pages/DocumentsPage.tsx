import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { ApiError, api } from "../api/client";
import type { DocumentDetail, DocumentOut, UploadLimits } from "../api/types";
import { EmptyState, ErrorState, LoadingPanel, Spinner } from "../components/Feedback";

const POLL_INTERVAL_MS = 2000;

const STATUS_META: Record<DocumentOut["status"], { label: string; className: string; icon: typeof Clock }> = {
  pending: { label: "Queued", className: "text-ink-muted border-edge", icon: Clock },
  processing: { label: "Indexing", className: "text-accent-soft border-accent/40", icon: Loader2 },
  ready: { label: "Ready", className: "text-success border-success/40", icon: CheckCircle2 },
  failed: { label: "Failed", className: "text-danger border-danger/40", icon: AlertCircle },
};

interface UploadTask {
  id: string;
  filename: string;
  progress: number;
  state: "uploading" | "indexing" | "done" | "error";
  error?: string;
}

export function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [limits, setLimits] = useState<UploadLimits | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<UploadTask[]>([]);
  const [dragging, setDragging] = useState(false);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await api.documents();
      setDocuments(response.documents);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load documents.");
    }
  }, []);

  useEffect(() => {
    void load();
    void api
      .uploadLimits()
      .then(setLimits)
      .catch(() => setLimits(null));
  }, [load]);

  // Poll only while something is still being indexed — a finished corpus does
  // not need a background request every two seconds.
  useEffect(() => {
    const hasActive = (documents ?? []).some(
      (document) => document.status === "pending" || document.status === "processing",
    );
    if (!hasActive) {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    pollRef.current = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, [documents, load]);

  const upload = useCallback(
    async (files: FileList | File[]) => {
      const allowed = limits?.allowed_extensions ?? [".pdf", ".txt", ".md"];
      const maxBytes = limits?.max_upload_size_bytes ?? 20 * 1024 * 1024;

      for (const file of Array.from(files)) {
        const taskId = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

        // Client-side checks mirror the server's so the user gets an immediate,
        // specific message instead of a 400 several seconds later.
        const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
        if (!allowed.includes(extension)) {
          setTasks((current) => [
            ...current,
            { id: taskId, filename: file.name, progress: 0, state: "error", error: `Unsupported type ${extension}` },
          ]);
          continue;
        }
        if (file.size > maxBytes) {
          setTasks((current) => [
            ...current,
            {
              id: taskId,
              filename: file.name,
              progress: 0,
              state: "error",
              error: `Too large (limit ${limits?.max_upload_size_mb ?? 20} MB)`,
            },
          ]);
          continue;
        }

        setTasks((current) => [...current, { id: taskId, filename: file.name, progress: 0, state: "uploading" }]);

        try {
          await api.uploadDocument(file, (percent) =>
            setTasks((current) =>
              current.map((task) => (task.id === taskId ? { ...task, progress: percent } : task)),
            ),
          );
          setTasks((current) =>
            current.map((task) => (task.id === taskId ? { ...task, progress: 100, state: "indexing" } : task)),
          );
          await load();
          // The document only becomes "ready" after background indexing, so the
          // task is closed once the poll reports it.
          setTasks((current) => current.filter((task) => task.id !== taskId));
        } catch (cause) {
          setTasks((current) =>
            current.map((task) =>
              task.id === taskId
                ? { ...task, state: "error", error: cause instanceof Error ? cause.message : "Upload failed" }
                : task,
            ),
          );
        }
      }
    },
    [limits, load],
  );

  async function reindex(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await api.reindexDocument(id);
      await load();
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await api.deleteDocument(id);
      if (detail?.id === id) setDetail(null);
      await load();
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setBusyId(null);
      setConfirming(null);
    }
  }

  async function openDetail(id: string) {
    setError(null);
    try {
      setDetail(await api.document(id));
    } catch (cause) {
      setError(describe(cause));
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-5 py-3.5">
        <div>
          <h1 className="text-sm font-semibold text-ink">Documents</h1>
          <p className="mt-0.5 text-xs text-ink-faint">
            {documents
              ? `${documents.length} uploaded · ${documents.filter((d) => d.status === "ready").length} ready`
              : "Loading…"}
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={() => fileInput.current?.click()}>
          <Upload className="size-4" aria-hidden="true" />
          Upload
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div className="mx-auto flex max-w-4xl flex-col gap-4">
          <input
            ref={fileInput}
            type="file"
            multiple
            className="sr-only"
            accept={limits?.allowed_extensions.join(",") ?? ".pdf,.txt,.md"}
            onChange={(event) => {
              if (event.target.files) void upload(event.target.files);
              event.target.value = "";
            }}
          />

          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (event.dataTransfer.files.length > 0) void upload(event.dataTransfer.files);
            }}
            className={`rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
              dragging ? "border-accent bg-accent/[0.07]" : "border-edge bg-surface"
            }`}
          >
            <Upload className="mx-auto size-6 text-ink-faint" aria-hidden="true" />
            <p className="mt-2.5 text-sm text-ink-muted">
              Drop {limits?.allowed_extensions.join(", ") ?? "PDF, TXT or Markdown"} files here
            </p>
            {limits && (
              <p className="mt-1 text-xs text-ink-faint">Up to {limits.max_upload_size_mb} MB each</p>
            )}
          </div>

          {tasks.length > 0 && (
            <div className="panel flex flex-col gap-2 p-3">
              {tasks.map((task) => (
                <div key={task.id} className="flex items-center gap-3 px-1 py-1 text-sm">
                  <span className="min-w-0 flex-1 truncate text-ink-muted">{task.filename}</span>
                  {task.state === "uploading" && (
                    <>
                      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-edge">
                        <span className="block h-full bg-accent transition-all" style={{ width: `${task.progress}%` }} />
                      </span>
                      <span className="font-mono text-xs text-ink-faint">{task.progress}%</span>
                    </>
                  )}
                  {task.state === "indexing" && (
                    <span className="flex items-center gap-1.5 text-xs text-accent-soft">
                      <Spinner className="size-3" /> indexing
                    </span>
                  )}
                  {task.state === "error" && (
                    <>
                      <span className="max-w-[16rem] truncate text-xs text-danger">{task.error}</span>
                      <button
                        type="button"
                        onClick={() => setTasks((current) => current.filter((item) => item.id !== task.id))}
                        aria-label={`Dismiss ${task.filename}`}
                        className="text-ink-faint hover:text-ink"
                      >
                        <X className="size-3.5" />
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}

          {error && <ErrorState message={error} onRetry={() => void load()} />}

          {documents === null ? (
            <LoadingPanel label="Loading documents" />
          ) : documents.length === 0 ? (
            <div className="panel">
              <EmptyState
                icon={<FileText className="size-6" aria-hidden="true" />}
                title="No documents yet"
                description="Upload a policy, handbook or benefits guide and the assistant will be able to answer questions about it."
                action={
                  <button type="button" className="btn-primary" onClick={() => fileInput.current?.click()}>
                    <Upload className="size-4" aria-hidden="true" />
                    Upload your first document
                  </button>
                }
              />
            </div>
          ) : (
            <ul className="panel divide-y divide-edge overflow-hidden">
              {documents.map((document) => {
                const meta = STATUS_META[document.status] ?? STATUS_META.pending;
                const Icon = meta.icon;
                return (
                  <li key={document.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <FileText className="size-4 shrink-0 text-ink-faint" aria-hidden="true" />
                    <button
                      type="button"
                      onClick={() => void openDetail(document.id)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <span className="block truncate text-sm text-ink">{document.filename}</span>
                      <span className="mt-0.5 block text-xs text-ink-faint">
                        {document.page_count > 0 && `${document.page_count} pages · `}
                        {document.chunk_count} chunks · {(document.size_bytes / 1024).toFixed(0)} KB
                      </span>
                      {document.status === "failed" && document.error_message && (
                        <span className="mt-1 block text-xs text-danger">{document.error_message}</span>
                      )}
                    </button>

                    <span className={`chip ${meta.className}`}>
                      <Icon className={`size-3 ${document.status === "processing" ? "animate-spin" : ""}`} aria-hidden="true" />
                      {meta.label}
                    </span>

                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        className="btn-ghost px-2.5 py-1.5"
                        onClick={() => void reindex(document.id)}
                        disabled={busyId === document.id}
                        title="Re-embed this document"
                      >
                        <RefreshCw className={`size-3.5 ${busyId === document.id ? "animate-spin" : ""}`} aria-hidden="true" />
                      </button>
                      {confirming === document.id ? (
                        <>
                          <button
                            type="button"
                            className="btn-danger px-2.5 py-1.5"
                            onClick={() => void remove(document.id)}
                            disabled={busyId === document.id}
                          >
                            Confirm
                          </button>
                          <button
                            type="button"
                            className="btn-ghost px-2.5 py-1.5"
                            onClick={() => setConfirming(null)}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="btn-ghost px-2.5 py-1.5 hover:border-danger/40 hover:text-danger"
                          onClick={() => setConfirming(document.id)}
                          title="Delete this document and its vectors"
                        >
                          <Trash2 className="size-3.5" aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {detail && (
            <div className="panel animate-fade-up">
              <div className="flex items-center justify-between gap-3 border-b border-edge px-4 py-3">
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-medium text-ink">{detail.filename}</h2>
                  <p className="mt-0.5 text-xs text-ink-faint">
                    {detail.chunks.length} stored chunks · {detail.collection_chunks} vectors in Qdrant
                  </p>
                </div>
                <button type="button" className="btn-ghost px-2.5 py-1.5" onClick={() => setDetail(null)} aria-label="Close preview">
                  <X className="size-3.5" aria-hidden="true" />
                </button>
              </div>
              <ul className="max-h-96 divide-y divide-edge overflow-y-auto">
                {detail.chunks.slice(0, 40).map((chunk) => (
                  <li key={chunk.chunk_index} className="px-4 py-3">
                    <p className="text-xs text-ink-faint">{chunk.citation || `Page ${chunk.page}`}</p>
                    <p className="mt-1 line-clamp-4 text-sm text-ink-muted">{chunk.text}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function describe(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 401 || cause.status === 403) return "This deployment requires a management token.";
    return cause.message;
  }
  if (cause instanceof Error) return cause.message;
  return String(cause);
}
