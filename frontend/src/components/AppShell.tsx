import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  BarChart3,
  FileText,
  History,
  Lock,
  MessageSquare,
  Moon,
  Sun,
  Unlock,
  Wifi,
  WifiOff,
} from "lucide-react";
import { HistoryDrawer } from "./HistoryDrawer";
import { useTheme } from "../hooks/useTheme";
import { getAuthToken, setAuthToken } from "../api/client";
import { useApp } from "../state/AppContext";

const NAV = [
  { to: "/", label: "Chat", icon: MessageSquare, end: true },
  { to: "/documents", label: "Documents", icon: FileText, end: false },
  { to: "/dashboard", label: "Dashboard", icon: BarChart3, end: false },
];

export function AppShell() {
  const { offline, loading, stats, auth, refreshAuth } = useApp();
  const { theme, toggle } = useTheme();
  const [historyOpen, setHistoryOpen] = useState(false);

  async function releaseToken() {
    setAuthToken(null);
    await refreshAuth();
  }

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <aside className="flex shrink-0 flex-row items-center justify-between gap-3 border-b border-edge bg-canvas/70 px-4 py-3 backdrop-blur-xl lg:h-full lg:w-60 lg:flex-col lg:items-stretch lg:justify-start lg:border-b-0 lg:border-r lg:py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-accent-deep text-white shadow-glow">
            <span className="text-sm font-bold">H</span>
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-ink">HR Nexus</p>
            <p className="text-[11px] text-ink-faint">Knowledge assistant</p>
          </div>
        </div>

        <nav aria-label="Main" className="flex gap-1 lg:mt-7 lg:flex-col">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-accent/12 text-accent-soft"
                    : "text-ink-muted hover:bg-surface-raised hover:text-ink"
                }`
              }
            >
              <Icon className="size-4 shrink-0" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
          <button
            type="button"
            onClick={() => setHistoryOpen(true)}
            className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-ink-muted transition-colors hover:bg-surface-raised hover:text-ink"
          >
            <History className="size-4 shrink-0" aria-hidden="true" />
            History
          </button>
        </nav>

        <div className="hidden lg:mt-auto lg:block">
          <ConnectionPill offline={offline} loading={loading} />
          {stats && (
            <p className="mt-2 px-3 text-[11px] leading-relaxed text-ink-faint">
              {stats.documents_indexed} documents · {stats.chunks_indexed} chunks indexed
            </p>
          )}

          <div className="mt-4 flex items-center gap-1.5 px-3">
            <IconButton
              label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              onClick={toggle}
            >
              {theme === "dark" ? <Sun className="size-3.5" aria-hidden="true" /> : <Moon className="size-3.5" aria-hidden="true" />}
            </IconButton>

            {auth?.auth_required &&
              (auth.verified && getAuthToken() ? (
                <IconButton label="Release the management token" onClick={() => void releaseToken()}>
                  <Lock className="size-3.5" aria-hidden="true" />
                </IconButton>
              ) : (
                <IconButton label="Management token required" disabled>
                  <Unlock className="size-3.5" aria-hidden="true" />
                </IconButton>
              ))}
          </div>
        </div>
      </aside>

      <main className="min-h-0 min-w-0 flex-1">
        <Outlet />
      </main>

      <HistoryDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </div>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className="rounded-lg border border-edge bg-surface-raised p-2 text-ink-muted transition-colors hover:border-edge-strong hover:text-ink disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function ConnectionPill({ offline, loading }: { offline: boolean; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 px-3 text-[11px] text-ink-faint">
        <span className="size-1.5 animate-pulse rounded-full bg-ink-faint" aria-hidden="true" />
        Connecting…
      </div>
    );
  }
  if (offline) {
    return (
      <div className="flex items-center gap-2 px-3 text-[11px] text-danger">
        <WifiOff className="size-3" aria-hidden="true" />
        API unreachable
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 px-3 text-[11px] text-success">
      <Wifi className="size-3" aria-hidden="true" />
      Connected
    </div>
  );
}
