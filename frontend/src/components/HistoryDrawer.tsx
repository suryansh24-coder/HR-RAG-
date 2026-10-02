import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { History, Loader2, MessageSquare, Plus, Trash2, X } from "lucide-react";
import { api } from "../api/client";
import type { ConversationOut } from "../api/types";

/**
 * Conversation history drawer.
 *
 * Reads `/api/conversations` — the same rows the backend persists for every
 * turn — and lets the user reopen, start a new thread or delete one. The list is
 * fetched each time the drawer opens, so a thread started in the chat view is
 * always current without a manual refresh.
 */
export function HistoryDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<ConversationOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await api.conversations();
      setConversations(response.conversations);
      setError(null);
    } catch (cause) {
      setConversations([]);
      setError(cause instanceof Error ? cause.message : "Could not load conversations.");
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  // Closing on Escape keeps the drawer usable without a pointer.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  async function remove(id: string) {
    setBusyId(id);
    try {
      await api.deleteConversation(id);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete the conversation.");
    } finally {
      setBusyId(null);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Conversation history">
      <button
        type="button"
        className="absolute inset-0 cursor-default bg-[var(--shadow-backdrop)] backdrop-blur-[2px]"
        onClick={onClose}
        aria-label="Close history"
        tabIndex={-1}
      />

      <aside className="animate-fade-up relative flex h-full w-full max-w-sm flex-col border-l border-edge bg-surface shadow-panel">
        <header className="flex items-center justify-between gap-3 border-b border-edge px-4 py-3.5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <History className="size-4 text-ink-faint" aria-hidden="true" />
            Conversation history
          </h2>
          <button type="button" className="btn-ghost px-2 py-1.5" onClick={onClose} aria-label="Close history">
            <X className="size-3.5" aria-hidden="true" />
          </button>
        </header>

        <div className="border-b border-edge px-4 py-3">
          <button
            type="button"
            className="btn-primary w-full"
            onClick={() => {
              navigate("/");
              onClose();
            }}
          >
            <Plus className="size-4" aria-hidden="true" />
            New conversation
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
          {error && <p className="px-1 pb-3 text-xs text-danger">{error}</p>}

          {conversations === null ? (
            <p className="flex items-center gap-2 px-1 py-6 text-sm text-ink-faint">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Loading…
            </p>
          ) : conversations.length === 0 ? (
            <p className="px-1 py-6 text-sm text-ink-faint">
              No conversations yet. Ask a question to start one.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {conversations.map((conversation) => (
                <li key={conversation.id} className="group flex items-center gap-1.5">
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-lg border border-transparent px-3 py-2.5 text-left transition-colors hover:border-edge hover:bg-surface-raised"
                    onClick={() => {
                      navigate(`/chat/${conversation.id}`);
                      onClose();
                    }}
                  >
                    <span className="flex items-center gap-1.5 text-sm text-ink">
                      <MessageSquare className="size-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
                      <span className="truncate">{conversation.title}</span>
                    </span>
                    <span className="pl-5 text-[11px] text-ink-faint">
                      {conversation.message_count} message{conversation.message_count === 1 ? "" : "s"}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="shrink-0 rounded-lg border border-transparent px-2 py-1.5 text-ink-faint transition-colors hover:border-danger/40 hover:text-danger"
                    onClick={() => void remove(conversation.id)}
                    disabled={busyId === conversation.id}
                    aria-label={`Delete conversation ${conversation.title}`}
                  >
                    {busyId === conversation.id ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
