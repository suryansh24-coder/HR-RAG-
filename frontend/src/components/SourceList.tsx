import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ExternalLink, FileText } from "lucide-react";
import { api, getAuthToken } from "../api/client";
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
            {source.document_id && <SourceDownloadLink documentId={source.document_id} filename={source.filename} />}
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

/**
 * Opens the cited file itself, so a user can confirm the quote against the source.
 *
 * This cannot be a plain `<a href>`: a protected deployment expects an
 * `Authorization` header, and a navigation request cannot carry one. The file is
 * therefore fetched with the normal client (which attaches the token) and handed
 * to the browser as an object URL.
 *
 * Object URLs pin the whole file in memory until they are revoked, so the URL is
 * revoked when it is replaced or when the card is closed. The grace period covers
 * a click that immediately collapses the card, so the URL outlives the navigation
 * it was created for.
 */
const REVOKE_GRACE_MS = 30_000;

function SourceDownloadLink({ documentId, filename }: { documentId: string; filename: string }) {
  const [error, setError] = useState<string | null>(null);
  const objectUrl = useRef<string | null>(null);

  // Released with a short grace period so a click that also collapses the card
  // does not revoke the URL out from under the navigation it just started.
  const release = useCallback((url: string) => {
    window.setTimeout(() => URL.revokeObjectURL(url), REVOKE_GRACE_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (objectUrl.current) release(objectUrl.current);
    };
  }, [release]);

  async function open() {
    setError(null);
    const token = getAuthToken();
    try {
      const response = await fetch(api.documentDownloadUrl(documentId), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`Could not open the file (${response.status}).`);
      const blob = await response.blob();
      // Releasing the previous click's URL keeps repeated opens from
      // accumulating copies of the file.
      if (objectUrl.current) release(objectUrl.current);
      const url = URL.createObjectURL(blob);
      objectUrl.current = url;
      const tab = window.open(url, "_blank", "noopener");
      if (!tab) {
        URL.revokeObjectURL(url);
        objectUrl.current = null;
        setError("Your browser blocked the new tab. Allow pop-ups to open the file.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not open the file.");
    }
  }

  return (
    <span className="inline-flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => void open()}
        title={`Open ${filename}`}
        aria-label={`Open the source file ${filename}`}
        className="inline-flex items-center gap-1 text-accent-soft hover:underline"
      >
        Open file
        <ExternalLink className="size-3" aria-hidden="true" />
      </button>
      {error && <span className="text-danger">{error}</span>}
    </span>
  );
}
