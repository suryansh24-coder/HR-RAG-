import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { AuthStatusResponse, MetaResponse, RagStatsResponse } from "../api/types";

interface AppState {
  meta: MetaResponse | null;
  stats: RagStatsResponse | null;
  auth: AuthStatusResponse | null;
  /** True while any of the bootstrap calls are outstanding. */
  loading: boolean;
  /** Set when the API is unreachable, so the shell can show a real error. */
  offline: boolean;
  error: string | null;
  refreshStats: () => Promise<void>;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [stats, setStats] = useState<RagStatsResponse | null>(null);
  const [auth, setAuth] = useState<AuthStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshStats = useCallback(async () => {
    try {
      setStats(await api.stats());
      setOffline(false);
    } catch {
      // A failed stats refresh is not fatal: individual screens still work.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const [metaResult, statsResult, authResult] = await Promise.allSettled([
          api.meta(),
          api.stats(),
          api.authStatus(),
        ]);
        if (cancelled) return;

        // Only a hard failure on every call counts as "offline"; partial
        // failures degrade individual features instead of blocking the UI.
        const allFailed =
          metaResult.status === "rejected" &&
          statsResult.status === "rejected" &&
          authResult.status === "rejected";

        if (allFailed) {
          setOffline(true);
          setError(
            metaResult.status === "rejected"
              ? describe(metaResult.reason)
              : "The API is unreachable.",
          );
        } else {
          setOffline(false);
          if (metaResult.status === "fulfilled") setMeta(metaResult.value);
          if (statsResult.status === "fulfilled") setStats(statsResult.value);
          if (authResult.status === "fulfilled") setAuth(authResult.value);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AppState>(
    () => ({ meta, stats, auth, loading, offline, error, refreshStats }),
    [meta, stats, auth, loading, offline, error, refreshStats],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

function describe(reason: unknown): string {
  if (reason instanceof Error) return reason.message;
  return String(reason);
}

export function useApp(): AppState {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used inside <AppProvider>");
  return context;
}

/** Convenience: the provider name, or `null` before stats load. */
export function useProviderName(): string | null {
  const { stats } = useApp();
  return stats?.config.llm_provider ?? null;
}
