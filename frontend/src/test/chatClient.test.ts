import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, streamChat } from "../api/client";
import { clearProfiles, saveProfile } from "../api/byok";

interface CapturedCall {
  url: string;
  init: RequestInit;
}

function captureFetch(
  response: unknown,
  extra: Partial<Response> = {},
): CapturedCall[] {
  const calls: CapturedCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit = {}) => {
      calls.push({ url: String(url), init });
      return Promise.resolve({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify(response)),
        ...extra,
      } as Response);
    }),
  );
  return calls;
}

function headersOf(init: RequestInit): Record<string, string> {
  return (init.headers ?? {}) as Record<string, string>;
}

/** A minimal `response.body` with a `getReader()` that yields the chunks once. */
function fakeBody(chunks: string[]) {
  let index = 0;
  return {
    getReader() {
      return {
        read: async () => {
          if (index < chunks.length) {
            const value = new TextEncoder().encode(chunks[index]);
            index += 1;
            return { value, done: false };
          }
          return { value: undefined, done: true };
        },
      };
    },
  };
}

beforeEach(() => {
  sessionStorage.clear();
  saveProfile({ provider: "groq", model: "llama-3.1-8b", apiKey: "sk-test" });
});

afterEach(() => {
  delete (window as unknown as { ReadableStream?: unknown }).ReadableStream;
  vi.unstubAllGlobals();
});

describe("chat BYOK headers", () => {
  it("adds the three headers to a normal chat request", async () => {
    const calls = captureFetch({ reply: "hi" });
    await api.chat({ message: "hi", mode: "general" });

    const headers = headersOf(calls[0].init);
    expect(headers["X-Synthia-LLM-Provider"]).toBe("groq");
    expect(headers["X-Synthia-LLM-Model"]).toBe("llama-3.1-8b");
    expect(headers["X-Synthia-LLM-API-Key"]).toBe("sk-test");
  });

  it("omits the headers when no profile is active", async () => {
    clearProfiles();
    const calls = captureFetch({ reply: "hi" });
    await api.chat({ message: "hi", mode: "general" });

    const headers = headersOf(calls[0].init);
    expect(headers["X-Synthia-LLM-Provider"]).toBeUndefined();
    expect(headers["X-Synthia-LLM-Model"]).toBeUndefined();
    expect(headers["X-Synthia-LLM-API-Key"]).toBeUndefined();
  });

  it("never sends the headers to unrelated endpoints", async () => {
    const calls = captureFetch({ providers: [], mode: "demo" });
    await api.providers();

    const headers = headersOf(calls[0].init);
    expect(headers["X-Synthia-LLM-Provider"]).toBeUndefined();
  });

  it("adds the headers to the streaming chat request", async () => {
    // Make the client believe a streaming body is available.
    (window as unknown as { ReadableStream: unknown }).ReadableStream =
      function ReadableStream() {};
    const body = fakeBody(['data: {"type": "done"}\n\n']) as unknown as ReadableStream;

    const calls = captureFetch({}, { body });
    await streamChat(
      { message: "hi", mode: "general" },
      { onToken: vi.fn(), onResult: vi.fn(), onError: vi.fn(), onDone: vi.fn() },
    );

    expect(calls[0].url).toContain("/api/chat/stream");
    const headers = headersOf(calls[0].init);
    expect(headers["X-Synthia-LLM-Provider"]).toBe("groq");
    expect(headers["X-Synthia-LLM-API-Key"]).toBe("sk-test");
  });

  it("preserves the headers in the non-streaming fallback", async () => {
    delete (window as unknown as { ReadableStream?: unknown }).ReadableStream;
    const calls = captureFetch(
      {
        id: "1",
        timestamp: "",
        mode: "general",
        operation: "conversation",
        reply: "hi",
        transcript: "hi",
        provider_used: "groq",
        tool_call: null,
        usage: null,
        warnings: [],
      },
    );
    const onError = vi.fn();
    await streamChat(
      { message: "hi", mode: "general" },
      { onToken: vi.fn(), onResult: vi.fn(), onError, onDone: vi.fn() },
    );

    expect(onError).not.toHaveBeenCalled();
    expect(calls[0].url).toContain("/api/chat");
    expect(headersOf(calls[0].init)["X-Synthia-LLM-Provider"]).toBe("groq");
  });
});
