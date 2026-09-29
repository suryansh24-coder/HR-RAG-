import { useState, type FormEvent, type ReactNode } from "react";
import { AlertTriangle, Inbox, Loader2, RefreshCw, ShieldAlert } from "lucide-react";
import { api, setAuthToken } from "../api/client";

export function Spinner({ className = "size-4" }: { className?: string }) {
  return <Loader2 className={`${className} animate-spin`} aria-hidden="true" />;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

/**
 * The single error surface for async panels.
 *
 * `retry` is optional but strongly preferred: an error the user cannot act on
 * is a dead end.
 */
export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-xl border border-danger/30 bg-danger/[0.06] px-6 py-10 text-center"
    >
      <AlertTriangle className="size-7 text-danger" aria-hidden="true" />
      <div>
        <p className="font-medium text-ink">{title}</p>
        <p className="mt-1 max-w-md text-sm text-ink-muted">{message}</p>
      </div>
      {onRetry && (
        <button type="button" className="btn-ghost" onClick={onRetry}>
          <RefreshCw className="size-4" aria-hidden="true" />
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="rounded-full border border-edge bg-surface-raised p-3 text-ink-faint">
        {icon ?? <Inbox className="size-6" aria-hidden="true" />}
      </div>
      <div>
        <p className="font-medium text-ink">{title}</p>
        <p className="mt-1 max-w-sm text-sm text-ink-muted">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function LoadingPanel({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 px-6 py-16 text-sm text-ink-muted">
      <Spinner />
      <span>{label}</span>
    </div>
  );
}

/**
 * Shown when the API demands a management token. The token is held in memory
 * only — see `setAuthToken` — so it is intentionally cleared on reload.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-md px-4 py-20">
      <div className="panel flex flex-col gap-4 p-7">
        <div className="flex items-center gap-2.5 text-ink">
          <ShieldAlert className="size-5 text-warning" aria-hidden="true" />
          <h1 className="text-lg font-semibold">Management token required</h1>
        </div>
        <p className="text-sm text-ink-muted">
          This deployment has <code className="font-mono text-ink">MANAGEMENT_TOKEN</code> enabled, so
          document and conversation changes need a bearer token. Reading questions does not.
        </p>
        <TokenForm />
        {children}
      </div>
    </div>
  );
}

function TokenForm() {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function verify(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setAuthToken(value);
    try {
      const status = await api.authStatus();
      if (status.verified) {
        window.location.reload();
      } else {
        setAuthToken(null);
        setError("That token was not accepted.");
      }
    } catch {
      setAuthToken(null);
      setError("Could not reach the API to verify the token.");
    }
  }

  return (
    <form onSubmit={verify} className="flex flex-col gap-3">
      <label className="text-sm font-medium text-ink" htmlFor="token">
        Token
      </label>
      <input
        id="token"
        type="password"
        className="field"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        autoComplete="off"
        placeholder="Paste your management token"
      />
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <button type="submit" className="btn-primary">
        Unlock
      </button>
    </form>
  );
}
