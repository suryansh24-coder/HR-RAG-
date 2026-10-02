import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Database,
  Gauge,
  MessageSquare,
  Search,
  ShieldCheck,
  Sparkles,
  FileText,
  Layers,
} from "lucide-react";
import { api } from "../api/client";
import type { QueryLogOut } from "../api/types";
import { ErrorState, LoadingPanel, Skeleton } from "../components/Feedback";
import { useApp } from "../state/AppContext";

/**
 * Starter questions. They are prompts only: each one hands off to /chat?q=...,
 * where it is answered by the same retrieval pipeline as any other question.
 */
const QUICK_QUESTIONS = [
  "How many days of annual leave do I get, and how is carry-over handled?",
  "What is the reimbursement limit for home office equipment?",
  "How does the probation period work, and when is it confirmed?",
  "What is the notice period for a voluntary resignation?",
];

export function DashboardPage() {
  const { stats, loading, error: appError, refreshStats } = useApp();
  const [queries, setQueries] = useState<QueryLogOut[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .recentQueries(8)
      .then((response) => {
        if (!cancelled) setQueries(response.entries);
      })
      .catch(() => {
        if (!cancelled) setQueries([]);
      });
    return () => {
      cancelled = true;
    };
  }, [stats?.queries_total]);

  if (loading && !stats) return <LoadingPanel label="Loading dashboard" />;
  if (appError) return <div className="p-6"><ErrorState message={appError} onRetry={() => void refreshStats()} /></div>;
  if (!stats) return <div className="p-6"><ErrorState message="Statistics are unavailable." onRetry={() => void refreshStats()} /></div>;

  const { metrics, config, collection } = stats;
  const groundedRatio = metrics.grounded_ratio;

  return (
    <div className="h-full overflow-y-auto px-5 py-5">
      <div className="mx-auto flex max-w-5xl flex-col gap-5">
        <Hero
          documentsIndexed={stats.documents_indexed}
          chunksIndexed={stats.chunks_indexed}
          provider={config.llm_provider}
          hasKnowledge={stats.chunks_indexed > 0}
          collectionStatus={collection.status}
        />

        <section aria-label="Key metrics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            icon={<FileText className="size-4" aria-hidden="true" />}
            label="Documents ready"
            value={stats.documents_indexed}
            hint={`${stats.documents_total} uploaded total`}
          />
          <StatCard
            icon={<Layers className="size-4" aria-hidden="true" />}
            label="Chunks indexed"
            value={stats.chunks_indexed}
            hint={collection.dimension ? `${collection.dimension}-dim vectors` : "dimension unknown"}
          />
          <StatCard
            icon={<MessageSquare className="size-4" aria-hidden="true" />}
            label="Questions asked"
            value={stats.queries_total}
            hint={`${stats.conversations_total} conversations`}
          />
          <StatCard
            icon={<ShieldCheck className="size-4" aria-hidden="true" />}
            label="Grounded answers"
            value={groundedRatio === null ? "—" : `${Math.round(groundedRatio * 100)}%`}
            hint={
              groundedRatio === null
                ? "no questions yet"
                : `${metrics.grounded_answers} of ${metrics.queries_total}`
            }
          />
        </section>

        <section aria-label="Quick questions" className="glass p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="flex items-center gap-2 text-sm font-medium text-ink">
              <Sparkles className="size-4 text-accent-soft" aria-hidden="true" />
              Start with a question
            </h2>
            <p className="text-xs text-ink-faint">
              Answered from your own documents, with citations.
            </p>
          </div>
          <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
            {QUICK_QUESTIONS.map((question) => (
              <Link
                key={question}
                to={`/chat?q=${encodeURIComponent(question)}`}
                className="glass-card group flex items-start justify-between gap-3 px-4 py-3.5 text-sm text-ink-muted"
              >
                <span className="min-w-0">{question}</span>
                <ArrowRight
                  className="mt-0.5 size-4 shrink-0 text-ink-faint transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-accent-soft"
                  aria-hidden="true"
                />
              </Link>
            ))}
          </div>
        </section>

        {stats.documents_failed > 0 && (
          <div
            role="status"
            className="glass-inset border-danger/30 bg-danger/[0.06] px-4 py-3 text-sm text-danger"
          >
            {stats.documents_failed} document{stats.documents_failed === 1 ? "" : "s"} failed to index.{" "}
            <Link to="/documents" className="underline">
              Review them
            </Link>
            .
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="glass p-5" aria-label="Latency">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-medium text-ink">
              <Gauge className="size-4 text-ink-faint" aria-hidden="true" />
              Latency
            </h2>
            {metrics.queries_total === 0 ? (
              <p className="text-sm text-ink-faint">No queries recorded yet.</p>
            ) : (
              <dl className="flex flex-col gap-2.5 text-sm">
                <LatencyRow label="Retrieval (avg)" value={metrics.avg_retrieval_ms} />
                <LatencyRow label="Retrieval (p95)" value={metrics.p95_retrieval_ms} />
                <LatencyRow label="Generation (avg)" value={metrics.avg_generation_ms} />
                <LatencyRow label="Total (avg)" value={metrics.avg_total_ms} />
                <LatencyRow label="Total (p95)" value={metrics.p95_total_ms} />
                <div className="mt-1 flex items-center justify-between border-t border-edge pt-2.5">
                  <dt className="text-ink-muted">Average top score</dt>
                  <dd className="font-mono text-xs text-ink">
                    {metrics.avg_top_score === null ? "—" : metrics.avg_top_score.toFixed(3)}
                  </dd>
                </div>
              </dl>
            )}
          </section>

          <section className="glass p-5" aria-label="Retrieval configuration">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-medium text-ink">
              <Search className="size-4 text-ink-faint" aria-hidden="true" />
              Retrieval configuration
            </h2>
            <dl className="flex flex-col gap-2.5 text-sm">
              <ConfigRow label="Answer provider" value={config.llm_provider} />
              <ConfigRow label="Embedding model" value={config.embedding_model} />
              <ConfigRow label="Similarity threshold" value={config.score_threshold.toFixed(2)} />
              <ConfigRow label="Top-K chunks" value={String(config.top_k)} />
              <ConfigRow label="Max chunks per document" value={String(config.max_chunks_per_document)} />
              <ConfigRow label="Chunk size" value={`${config.chunk_size} chars`} />
              <ConfigRow label="Vector store" value={`${config.qdrant_mode} (${config.qdrant_collection})`} />
            </dl>
          </section>

          <section className="glass p-5" aria-label="Vector store">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-medium text-ink">
              <Database className="size-4 text-ink-faint" aria-hidden="true" />
              Vector store
            </h2>
            <dl className="flex flex-col gap-2.5 text-sm">
              <ConfigRow label="Status" value={collection.status} />
              <ConfigRow label="Points" value={collection.points_count.toLocaleString()} />
              <ConfigRow label="Indexed vectors" value={collection.indexed_vectors_count.toLocaleString()} />
              <ConfigRow label="Distance metric" value={collection.distance ?? "—"} />
            </dl>
          </section>

          <section className="glass p-5" aria-label="Recent questions">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-medium text-ink">
              <Activity className="size-4 text-ink-faint" aria-hidden="true" />
              Recent questions
            </h2>
            {queries === null ? (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            ) : queries.length === 0 ? (
              <p className="text-sm text-ink-faint">Nothing asked yet.</p>
            ) : (
              <ul className="flex flex-col gap-2.5">
                {queries.map((entry) => (
                  <li key={entry.id} className="flex items-start gap-2.5 text-sm">
                    <span
                      className={`mt-1.5 size-1.5 shrink-0 rounded-full ${
                        entry.grounded ? "bg-success" : "bg-warning"
                      }`}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-ink-muted">{entry.question_preview}</span>
                      <span className="mt-0.5 block text-[11px] text-ink-faint">
                        {entry.grounded ? `${entry.chunks_retrieved} chunks` : "no context"} ·{" "}
                        {entry.total_latency_ms === null ? "—" : `${Math.round(entry.total_latency_ms)} ms`}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <p className="pb-4 text-center text-[11px] text-ink-faint">
          {metrics.uptime_seconds > 0 &&
            `Uptime ${formatDuration(metrics.uptime_seconds)} · `}
          {config.llm_provider === "extractive"
            ? "Answers are quoted extracts from your documents, not generated prose."
            : `Answers generated by ${config.llm_model}.`}
          {" Every figure above is read live from the API."}
        </p>
      </div>
    </div>
  );
}

function Hero({
  documentsIndexed,
  chunksIndexed,
  provider,
  hasKnowledge,
  collectionStatus,
}: {
  documentsIndexed: number;
  chunksIndexed: number;
  provider: string;
  hasKnowledge: boolean;
  collectionStatus: string;
}) {
  return (
    <section className="glass glass-sheen relative overflow-hidden px-6 py-7" aria-label="Overview">
      <div className="relative flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-xl">
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-accent-soft">
            HR Nexus
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">
            Ask your HR policies anything.
          </h1>
          <p className="mt-2.5 text-sm leading-relaxed text-ink-muted">
            {hasKnowledge
              ? `${documentsIndexed} document${documentsIndexed === 1 ? "" : "s"} indexed into ${chunksIndexed.toLocaleString()} searchable passages. Answers quote those passages and cite the source, and when nothing relevant exists the assistant says so instead of guessing.`
              : "Your knowledge base is empty. Upload a policy to get started. Until then the assistant will say it cannot find an answer rather than inventing one."}
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-2.5">
            <Link to="/chat" className="btn-primary">
              <MessageSquare className="size-4" aria-hidden="true" />
              Ask a question
            </Link>
            <Link to="/documents" className="btn-ghost">
              <FileText className="size-4" aria-hidden="true" />
              {hasKnowledge ? "Manage documents" : "Upload a document"}
            </Link>
          </div>
        </div>

        <dl className="grid shrink-0 gap-2.5 sm:min-w-64">
          {/* `/rag/stats` answered this render, so the API itself is up; the
              collection status below is the vector store's own health. */}
          <StatusPill label="API" ok detail="healthy" />
          <StatusPill
            label="Answer provider"
            ok={provider !== "none"}
            detail={provider === "extractive" ? "extractive (offline)" : provider}
          />
          <StatusPill
            label="Vector store"
            ok={collectionStatus === "green"}
            detail={collectionStatus}
          />
        </dl>
      </div>
    </section>
  );
}

function StatusPill({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div className="glass-inset flex items-center gap-2.5 px-3.5 py-2.5">
      <span
        className={`size-1.5 shrink-0 rounded-full ${ok ? "bg-success" : "bg-warning"}`}
        aria-hidden="true"
      />
      <dt className="text-[11px] uppercase tracking-wider text-ink-faint">{label}</dt>
      <dd className="ml-auto truncate font-mono text-xs text-ink" title={detail}>
        {detail}
      </dd>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="glass p-4">
      <div className="flex items-center gap-2 text-ink-faint">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
      </div>
      <p className="mt-2.5 text-2xl font-semibold tabular-nums text-ink">{value}</p>
      <p className="mt-1 text-xs text-ink-faint">{hint}</p>
    </div>
  );
}

function LatencyRow({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="font-mono text-xs text-ink">
        {value === null ? "—" : `${value < 10 ? value.toFixed(1) : Math.round(value)} ms`}
      </dd>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="shrink-0 text-ink-muted">{label}</dt>
      <dd className="truncate font-mono text-xs text-ink" title={value}>
        {value}
      </dd>
    </div>
  );
}

function formatDuration(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}
