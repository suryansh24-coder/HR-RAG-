import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Bot, Copy, Check, Send, Square, User, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ApiError, api, streamChat } from "../api/client";
import type { ConversationDetail, SourceOut, StreamEvent } from "../api/types";
import { SourceList } from "../components/SourceList";
import { ErrorState, Spinner } from "../components/Feedback";
import { useApp } from "../state/AppContext";

interface LocalMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceOut[];
  noContext: boolean;
  suggestions: string[];
}

/** Stages that mean "we are working". Used to drive the progress indicator. */
const ACTIVE_STAGES = new Set(["retrieving", "sources", "generating"]);

const STAGE_LABEL: Record<string, string> = {
  retrieving: "Searching your HR documents",
  sources: "Reading the most relevant passages",
  generating: "Composing a grounded answer",
};

function greeting(): LocalMessage {
  return {
    id: "welcome",
    role: "assistant",
    content:
      "Ask me anything about your HR policies — leave, expenses, security, performance reviews. " +
      "Every answer is quoted from your own documents, and I will tell you when I cannot find something.",
    sources: [],
    noContext: false,
    suggestions: [],
  };
}

export function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { stats } = useApp();

  const [messages, setMessages] = useState<LocalMessage[]>([greeting()]);
  const [input, setInput] = useState("");
  const [stage, setStage] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  // The thread this screen is talking to. The first question on `/` has no id
  // yet, so it is learned from the stream's `start` event and then reused — the
  // server keys a conversation off the id it hands back, and sending `null` again
  // would start a brand new conversation on every turn.
  const [activeId, setActiveId] = useState<string | null>(conversationId ?? null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const autoAskedRef = useRef(false);
  /** Conversation id this screen streamed itself — see the history effect below. */
  const streamedIdRef = useRef<string | null>(null);

  /**
   * The conversation this screen is showing.
   *
   * Two spellings are accepted: `/chat/<id>` (a deep link or a history click)
   * and `/?conversation=<id>` (the id the stream handed back mid-answer). The
   * query form exists because changing the *path* re-keys the route element and
   * remounts this screen, which would throw away the answer being streamed.
   */
  const threadId = conversationId ?? searchParams.get("conversation");

  // Load history when the route carries a conversation id.
  useEffect(() => {
    setActiveId(threadId);
    if (!threadId) {
      setMessages([greeting()]);
      return;
    }
    // The id arriving mid-stream marks the transition this screen just made:
    // re-reading the thread at that moment would replace the answer we are still
    // receiving with a snapshot taken before it was persisted.
    if (streamedIdRef.current === threadId) {
      streamedIdRef.current = null;
      return;
    }
    let cancelled = false;
    setError(null);

    (async () => {
      try {
        const detail: ConversationDetail = await api.conversation(threadId);
        if (cancelled) return;
        const history = detail.messages.map<LocalMessage>((message) => ({
          id: message.id,
          role: message.role === "user" ? "user" : "assistant",
          content: message.content,
          sources: message.sources ?? [],
          noContext: message.no_context,
          suggestions: [],
        }));
        setMessages(history.length > 0 ? history : [greeting()]);
      } catch (cause) {
        if (!cancelled) setError(describe(cause));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [threadId]);

  // Pin to the newest message as content grows.
  useEffect(() => {
    const node = scrollRef.current;
    // Guarded: `scrollTo` is absent in jsdom and in some older embedded browsers.
    if (node && typeof node.scrollTo === "function") {
      node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
    }
  }, [messages, stage]);

  // Abort any in-flight stream if the component goes away.
  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || streaming) return;

      const userMessage: LocalMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: trimmed,
        sources: [],
        noContext: false,
        suggestions: [],
      };
      const answerId = `assistant-${Date.now()}`;

      setMessages((current) => [
        ...current,
        userMessage,
        { id: answerId, role: "assistant", content: "", sources: [], noContext: false, suggestions: [] },
      ]);
      setInput("");
      setError(null);
      setStage("retrieving");
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const patch = (change: Partial<LocalMessage>) =>
        setMessages((current) =>
          current.map((message) => (message.id === answerId ? { ...message, ...change } : message)),
        );

      try {
        await streamChat(trimmed, activeId, {
          signal: controller.signal,
          onEvent: (event: StreamEvent) => {
            if (event.stage === "start") {
              const id = event.data.conversation_id ? String(event.data.conversation_id) : null;
              if (id) {
                setActiveId(id);
                // Keep the address bar in step so a reload or a shared link reopens
                // this thread. The id goes in the query string, not the path:
                // changing the path would remount this screen mid-answer.
                if (id !== threadId) {
                  streamedIdRef.current = id;
                  navigate(`/?conversation=${encodeURIComponent(id)}`, { replace: true });
                }
              }
              return;
            }
            if (event.stage === "error") {
              setError(event.message || "The assistant could not answer that.");
              setStage(null);
              return;
            }
            if (event.stage === "complete") {
              patch({
                content: String(event.data.answer ?? ""),
                sources: (event.data.sources as SourceOut[] | undefined) ?? [],
                noContext: Boolean(event.data.no_context),
                // Follow-ups are derived server-side from the sources that were
                // really retrieved, so they are always answerable questions.
                suggestions: (event.data.suggestions as string[] | undefined) ?? [],
              });
              setStage(null);
              return;
            }
            if (event.stage === "sources") {
              // Sources arrive before the answer text, so the citations can be
              // shown while generation is still running.
              patch({ sources: (event.data.sources as SourceOut[] | undefined) ?? [] });
            }
            if (ACTIVE_STAGES.has(event.stage)) setStage(event.stage);
          },
        });
      } catch (cause) {
        if (controller.signal.aborted) {
          // Keep whatever partial answer already arrived.
        } else {
          setError(describe(cause));
          setStage(null);
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        setMessages((current) => {
          const last = current[current.length - 1];
          // Drop an assistant bubble that never received any content.
          if (last && last.id === answerId && !last.content && !last.noContext) {
            return current.slice(0, -1);
          }
          return current;
        });
      }
    },
    [activeId, threadId, navigate, streaming],
  );

  // Hand-off from the dashboard: `/chat?q=How many annual leaves…` asks that
  // question straight away. Guarded so re-renders (or StrictMode's double mount)
  // cannot fire the same question twice, and only `q` is dropped afterwards so a
  // refresh does not re-ask it and `?conversation=` survives.
  useEffect(() => {
    const question = searchParams.get("q");
    if (!question || autoAskedRef.current) return;
    autoAskedRef.current = true;
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    setSearchParams(next, { replace: true });
    void send(question);
  }, [searchParams, send, setSearchParams]);

  // Put the cursor in the composer on load; the dashboard link lands here too.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
    setStage(null);
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(text);
      setTimeout(() => setCopied(null), 1600);
    } catch {
      /* clipboard blocked — not worth interrupting the user over */
    }
  }

  const provider = stats?.config.llm_provider ?? null;
  const suggestions = messages[messages.length - 1]?.suggestions ?? [];
  const groundedRatio = stats?.metrics.grounded_ratio ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge bg-canvas/60 px-5 py-3.5 backdrop-blur-xl">
        <div>
          <h1 className="text-sm font-semibold text-ink">Ask a question</h1>
          <p className="mt-0.5 text-xs text-ink-faint">
            Answers are grounded in your uploaded documents, with citations.
          </p>
        </div>
        {provider && (
          <span className="chip" title={provider === "extractive" ? "Quotes the most relevant sentences from your documents instead of generating prose." : undefined}>
            <Sparkles className="size-3" aria-hidden="true" />
            {provider === "extractive" ? "Extractive mode" : provider}
          </span>
        )}
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-5">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              streaming={streaming && message.id.startsWith("assistant-") && !message.content}
              onCopy={copy}
              copied={copied}
            />
          ))}

          {stage && (
            <div className="flex items-center gap-2.5 text-sm text-ink-muted" role="status">
              <Spinner />
              {STAGE_LABEL[stage] ?? "Working"}
            </div>
          )}

          {error && <ErrorState title="Request failed" message={error} onRetry={() => setError(null)} />}

          {suggestions.length > 0 && !streaming && (
            <div className="flex flex-wrap gap-2">
              {suggestions.map((suggestion) => (
                <button key={suggestion} type="button" className="chip hover:border-accent/50" onClick={() => send(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>
          )}

          {messages.length === 1 && (
            <div className="grid gap-2.5 sm:grid-cols-2">
              {[
                "What is the annual leave entitlement?",
                "How many office days per week do hybrid employees need to attend?",
                "What is the reimbursement limit for home office equipment?",
                "How does the performance review cycle work?",
              ].map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => send(example)}
                  className="glass-card px-4 py-3.5 text-left text-sm text-ink-muted"
                >
                  {example}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <footer className="border-t border-edge bg-canvas/70 px-5 py-3.5 backdrop-blur-xl">
        <form
          className="glass-inset mx-auto flex max-w-3xl items-end gap-2.5 p-2"
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
        >
          <textarea
            ref={inputRef}
            className="field max-h-40 min-h-[46px] resize-y border-transparent bg-transparent py-3 focus:border-transparent"
            placeholder="Ask about leave, expenses, security, performance…"
            value={input}
            rows={1}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send(input);
              }
            }}
            disabled={streaming}
            aria-label="Your question"
          />
          {streaming ? (
            <button type="button" className="btn-ghost" onClick={stop}>
              <Square className="size-4" aria-hidden="true" />
              Stop
            </button>
          ) : (
            <button type="submit" className="btn-primary" disabled={!input.trim()}>
              <Send className="size-4" aria-hidden="true" />
              Ask
            </button>
          )}
        </form>
        {groundedRatio !== null && (
          <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-ink-faint">
            {Math.round(groundedRatio * 100)}% of questions so far were answered from your documents.
          </p>
        )}
      </footer>
    </div>
  );
}

function MessageBubble({
  message,
  streaming,
  onCopy,
  copied,
}: {
  message: LocalMessage;
  streaming: boolean;
  onCopy: (text: string) => void;
  copied: string | null;
}) {
  const isUser = message.role === "user";

  return (
    <article className={`animate-fade-up flex gap-3.5 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border ${
          isUser ? "border-edge bg-surface-raised text-ink-muted" : "border-accent/35 bg-accent/12 text-accent-soft"
        }`}
        aria-hidden="true"
      >
        {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
      </div>

      <div className={`min-w-0 flex-1 ${isUser ? "items-end" : ""}`}>
        <div
          className={`glass-sheen inline-block max-w-full rounded-xl px-4 py-3 text-sm leading-relaxed ${
            // User turns keep a tinted fill (rather than a solid accent) so the
            // markdown inside stays legible in both themes.
            isUser
              ? "border border-accent/25 bg-accent/12 text-ink"
              : "glass text-ink-muted"
          }`}
        >
          {message.content ? (
            <div className={isUser ? "" : "prose-invert max-w-none"}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5">{children}</ul>,
                  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5">{children}</ol>,
                  li: ({ children }) => <li>{children}</li>,
                  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
                  code: ({ children }) => (
                    <code className="rounded bg-surface-sunken px-1 py-0.5 font-mono text-xs text-accent-soft">
                      {children}
                    </code>
                  ),
                  a: ({ children, href }) => (
                    <a href={href} className="text-accent-soft underline" target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  ),
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          ) : streaming ? (
            <span className="flex items-center gap-2 text-ink-faint">
              <Spinner className="size-3.5" />
              Composing…
            </span>
          ) : null}
        </div>

        {!isUser && (message.sources.length > 0 || message.noContext) && (
          <div className="mt-2">
            {message.noContext ? (
              <p className="chip border-warning/35 bg-warning/10 text-warning">
                No matching passage in your documents — nothing was invented.
              </p>
            ) : (
              <SourceList sources={message.sources} />
            )}
          </div>
        )}

        {!isUser && message.content && (
          <button
            type="button"
            onClick={() => onCopy(message.content)}
            className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-ink-faint transition-colors hover:text-ink-muted"
          >
            {copied === message.content ? (
              <>
                <Check className="size-3" aria-hidden="true" /> Copied
              </>
            ) : (
              <>
                <Copy className="size-3" aria-hidden="true" /> Copy answer
              </>
            )}
          </button>
        )}
      </div>
    </article>
  );
}

function describe(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 0) return cause.message;
    if (cause.status === 429) return "Too many questions in a row. Wait a moment and try again.";
    if (cause.status === 401 || cause.status === 403) return "This action needs a valid management token.";
    return cause.message;
  }
  if (cause instanceof Error) return cause.message;
  return String(cause);
}
