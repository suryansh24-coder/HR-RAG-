import { useState } from "react";
import { ChevronDown, ExternalLink, FileText } from "lucide-react";
import type { SourceOut } from "../api/types";

/**
 * Score is the *hybrid* score (0.65 cosine + 0.35 lexical coverage), not a
 * probability that the answer is correct. The bar is therefore a relative
 * confidence signal, and the label says so rather than implying a percentage.
 */
function confidenceLabel(score: number): { label: string; tone: string } {
  if (score >= 0.75) return { label: "Strong match", tone: "text-success" };
  if (score >= 0.6) return { label: "Good match", tone: "text-ink-muted" };
  return { label: "Weakest match", tone: "text-warning" };
}

export function SourceCard({ source, index }: { source: SourceOut; index: number }) {
  const [open, setOpen] = useState(false);
  const { label, tone } = confidenceLabel(source.score);
  const percent = Math.round(Math.min(source.score, 1) * 100);

  return (
    <div className="overflow-hidden rounded-lg border border-edge bg-surface-sunken">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-surface-raised"
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-accent/15 text-[11px] font-semibold text-accent-soft">
          {index + 1}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
            <FileText className="size-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
            <span className="truncate">{source.filename}</span>
          </span>
          <span className="mt-0.5 flex items-center gap-2 text-xs text-ink-faint">
            <span>
              {source.citation || `Page ${source.page}, chunk ${source.chunk_index}`}
            </span>
            <span aria-hidden="true">·</span>
            <span className={tone}>{label}</span>
          </span>
        </span>
        <span className="hidden w-24 shrink-0 sm:block">
          <span className="block h-1.5 overflow-hidden rounded-full bg-edge">
            <span
              className="block h-full rounded-full bg-accent/80"
              style={{ width: `${percent}%` }}
            />
          </span>
          <span className="mt-1 block text-right font-mono text-[10px] text-ink-faint">
            {source.score.toFixed(3)}
          </span>
        </span>
        <ChevronDown
          className={`size-4 shrink-0 text-ink-faint transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="animate-fade-up border-t border-edge px-3.5 py-3">
          <p className="text-sm leading-relaxed text-ink-muted">{source.snippet}</p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11px] text-ink-faint">
            <span className="chip">{source.document_type || "document"}</span>
            <span className="chip">page {source.page}</span>
            <span className="chip">chunk {source.chunk_index}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function SourceList({
  sources,
  title = "Sources",
}: {
  sources: SourceOut[];
  title?: string;
}) {
  if (sources.length === 0) return null;

  return (
    <section aria-label={title} className="mt-4">
      <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-faint">
        {title}
        <span className="rounded-full bg-surface-raised px-1.5 py-0.5 text-[10px] text-ink-muted">
          {sources.length}
        </span>
      </h3>
      <div className="flex flex-col gap-1.5">
        {sources.map((source, index) => (
          <SourceCard key={`${source.chunk_id}-${index}`} source={source} index={index} />
        ))}
      </div>
    </section>
  );
}

/** Link out to a source document file; only useful when auth allows downloads. */
export function SourceDownloadLink({ documentId, filename }: { documentId: string; filename: string }) {
  return (
    <a
      href={`/api/documents/${documentId}/file`}
      className="inline-flex items-center gap-1 text-xs text-accent-soft hover:underline"
      target="_blank"
      rel="noreferrer"
    >
      {filename}
      <ExternalLink className="size-3" aria-hidden="true" />
    </a>
  );
}
