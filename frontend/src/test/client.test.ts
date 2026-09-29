import { describe, expect, it, vi } from "vitest";
import { ApiError, api, streamChat } from "../api/client";
import type { StreamEvent } from "../api/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Build a ReadableStream that yields the given chunks to the SSE parser. */
function sseStream(blocks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const block of blocks) controller.enqueue(encoder.encode(block));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("api client", () => {
  it("unwraps FastAPI error detail into ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Document not found", code: "not_found" }, 404)),
    );

    const error = await api.documents().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("Document not found");
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).code).toBe("not_found");
  });

  it("surfaces FastAPI validation errors with their message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: [{ msg: "question too long" }] }, 422),
      ),
    );

    const error = (await api.chat("x").catch((cause: unknown) => cause)) as ApiError;
    expect(error.message).toBe("question too long");
    expect(error.status).toBe(422);
  });

  it("falls back to a generic message on a non-JSON error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>502</html>", { status: 502 })),
    );

    const error = (await api.meta().catch((cause: unknown) => cause)) as ApiError;
    expect(error.status).toBe(502);
    expect(error.message).toContain("502");
  });

  it("attaches a bearer token when one is set", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ entries: [], total: 0 })));
    const { setAuthToken } = await import("../api/client");
    setAuthToken("secret-token");

    await api.recentQueries();
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((call?.[1] as RequestInit).headers).toMatchObject({ Authorization: "Bearer secret-token" });

    setAuthToken(null);
  });
});

describe("streamChat", () => {
  it("reassembles events split across network chunks", async () => {
    // The SSE frame is deliberately cut mid-JSON: a naive line reader would
    // drop the second half and the answer would never arrive.
    const frame =
      'event: complete\ndata: {"answer":"25 days","no_context":false,"sources":[]}\n\n';
    const split = Math.floor(frame.length / 2);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseStream([frame.slice(0, split), frame.slice(split)])));

    const events: StreamEvent[] = [];
    await streamChat("leave?", null, { onEvent: (event) => events.push(event) });

    expect(events).toHaveLength(1);
    expect(events[0]?.stage).toBe("complete");
    expect(events[0]?.data.answer).toBe("25 days");
  });

  it("handles several events in one chunk", async () => {
    const payload =
      'event: retrieving\ndata: {"message":"Searching"}\n\n' +
      'event: sources\ndata: {"message":"Reading","sources":[{"filename":"a.pdf"}]}\n\n' +
      'event: complete\ndata: {"answer":"done"}\n\n';

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseStream([payload])));

    const events: StreamEvent[] = [];
    await streamChat("q", null, { onEvent: (event) => events.push(event) });

    expect(events.map((event) => event.stage)).toEqual(["retrieving", "sources", "complete"]);
    expect(events[1]?.data.sources).toHaveLength(1);
  });

  it("emits an error event and resolves, so the UI can show it", async () => {
    const payload = 'event: error\ndata: {"message":"rate limited","code":"rate_limited"}\n\n';
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseStream([payload])));

    const events: StreamEvent[] = [];
    await streamChat("q", null, { onEvent: (event) => events.push(event) });

    expect(events[0]?.stage).toBe("error");
    expect(events[0]?.message).toBe("rate limited");
  });

  it("throws when the stream ends without a terminal event", async () => {
    // A dropped connection must not look like a successful, empty answer.
    const payload = 'event: retrieving\ndata: {"message":"Searching"}\n\n';
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseStream([payload])));

    await expect(streamChat("q", null, { onEvent: () => {} })).rejects.toBeInstanceOf(ApiError);
  });

  it("rejects with ApiError when the request itself fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "nope" }, 400)));
    await expect(streamChat("q", null, { onEvent: () => {} })).rejects.toBeInstanceOf(ApiError);
  });
});
