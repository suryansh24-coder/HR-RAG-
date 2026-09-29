import { NavLink, Outlet } from "react-router-dom";
import { BarChart3, FileText, MessageSquare, Wifi, WifiOff } from "lucide-react";
import { useApp } from "../state/AppContext";

const NAV = [
  { to: "/", label: "Chat", icon: MessageSquare, end: true },
  { to: "/documents", label: "Documents", icon: FileText, end: false },
  { to: "/dashboard", label: "Dashboard", icon: BarChart3, end: false },
];

export function AppShell() {
  const { offline, loading, stats } = useApp();

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <aside className="flex shrink-0 flex-row items-center justify-between gap-3 border-b border-edge bg-surface px-4 py-3 lg:h-full lg:w-60 lg:flex-col lg:items-stretch lg:justify-start lg:border-b-0 lg:border-r lg:py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-accent text-white">
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
        </nav>

        <div className="hidden lg:mt-auto lg:block">
          <ConnectionPill offline={offline} loading={loading} />
          {stats && (
            <p className="mt-2 px-3 text-[11px] leading-relaxed text-ink-faint">
              {stats.documents_indexed} documents · {stats.chunks_indexed} chunks indexed
            </p>
          )}
        </div>
      </aside>

      <main className="min-h-0 min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
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
