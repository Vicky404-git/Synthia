import type {
  ApiErrorBody,
  ChatResponse,
  HealthResponse,
  Mode,
  ProviderListResponse,
  ReadyResponse,
  ToolExecuteResponse,
  ToolListResponse,
  TranscriptionStatus,
  InputSource,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

// The API token is never baked into the build. It is entered at runtime in
// Settings and kept in sessionStorage for the current browser session only.
const TOKEN_KEY = "synthia.api.token";
let apiToken = (() => {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
})();

export function setApiToken(token: string): void {
  apiToken = token.trim();
  try {
    if (apiToken) sessionStorage.setItem(TOKEN_KEY, apiToken);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* sessionStorage may be unavailable */
  }
}

export function hasApiToken(): boolean {
  return apiToken.length > 0;
}

export function getApiToken(): string {
  return apiToken;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(code: string, message: string, status: number, details = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function authHeaders(): Record<string, string> {
  return apiToken ? { Authorization: `Bearer ${apiToken}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(
      "network_failure",
      "Could not reach the Synthia backend.",
      0,
    );
  }
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const body = payload as ApiErrorBody | null;
    const err = body?.error;
    throw new ApiError(
      err?.code ?? "http_error",
      err?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      err?.details ?? {},
    );
  }
  return payload as T;
}

export interface ChatHistoryMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatPayload {
  message: string;
  mode: Mode;
  history?: ChatHistoryMessage[];
  confirmed?: boolean;
  session_id?: string;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  ready: () => request<ReadyResponse>("/ready"),
  providers: () => request<ProviderListResponse>("/api/providers"),
  tools: () => request<ToolListResponse>("/api/tools"),
  chat: (payload: ChatPayload) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  executeTool: (
    name: string,
    args: Record<string, unknown>,
    confirmed = false,
  ) =>
    request<ToolExecuteResponse>("/api/tools/execute", {
      method: "POST",
      body: JSON.stringify({ name, arguments: args, confirmed }),
    }),
  recordTranscription: (payload: {
    transcript: string;
    provider: string;
    language?: string | null;
    source: InputSource;
    status: TranscriptionStatus;
    confidence?: number | null;
    parsed_intent?: string | null;
    tool_name?: string | null;
    tool_status?: TranscriptionStatus | null;
    error?: Record<string, unknown> | null;
    duration_ms?: number | null;
  }) =>
    request<unknown>("/api/transcriptions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export interface StreamHandlers {
  onToken: (value: string) => void;
  onResult: (response: ChatResponse) => void;
  onError: (error: ApiError) => void;
  onDone: () => void;
}

/**
 * Stream a chat request as SSE. Falls back to a non-streaming request when the
 * browser lacks streaming fetch support.
 */
export async function streamChat(
  payload: ChatPayload,
  handlers: StreamHandlers,
): Promise<void> {
  if (typeof fetch !== "function" || !window.ReadableStream) {
    try {
      const response = await api.chat(payload);
      handlers.onResult(response);
      handlers.onDone();
    } catch (error) {
      handlers.onError(
        error instanceof ApiError
          ? error
          : new ApiError("provider_error", String(error), 0),
      );
    }
    return;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    });
  } catch {
    handlers.onError(
      new ApiError("network_failure", "Could not reach the Synthia backend.", 0),
    );
    return;
  }

  if (!response.ok || !response.body) {
    // Fall back to the non-streaming endpoint for a structured error.
    try {
      const fallback = await api.chat(payload);
      handlers.onResult(fallback);
      handlers.onDone();
    } catch (error) {
      handlers.onError(
        error instanceof ApiError
          ? error
          : new ApiError("provider_error", String(error), 0),
      );
    }
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handleEvent = (raw: string) => {
    const line = raw.trim();
    if (!line.startsWith("data:")) return;
    const data = line.slice(5).trim();
    if (!data) return;
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(data);
    } catch {
      return;
    }
    if (event.type === "token") {
      handlers.onToken(String(event.value ?? ""));
    } else if (event.type === "result") {
      handlers.onResult(event.response as ChatResponse);
    } else if (event.type === "done") {
      if (event.response) handlers.onResult(event.response as ChatResponse);
      handlers.onDone();
    } else if (event.type === "error") {
      const err = event.error as { code: string; message: string; details?: Record<string, unknown> };
      handlers.onError(
        new ApiError(err.code, err.message, 0, err.details ?? {}),
      );
    }
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) handleEvent(part);
    }
    if (buffer) handleEvent(buffer);
  } catch {
    handlers.onError(
      new ApiError("network_failure", "The stream was interrupted.", 0),
    );
  }
}
