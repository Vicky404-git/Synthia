import { afterEach, describe, expect, it, vi } from "vitest";
import { mapSpeechError } from "../stt/browser";
import {
  BrowserSttProvider,
  createSttProvider,
  ServerSttProvider,
} from "../stt";
import { STATUS_META } from "../history/status";
import type { TranscriptionStatus } from "../api/types";

describe("stt provider selection", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("defaults to server STT (local Faster-Whisper)", () => {
    vi.stubEnv("VITE_STT_PROVIDER", "");
    expect(createSttProvider()).toBeInstanceOf(ServerSttProvider);
  });

  it("honours an explicitly configured provider", () => {
    vi.stubEnv("VITE_STT_PROVIDER", "browser");
    expect(createSttProvider()).toBeInstanceOf(BrowserSttProvider);
    vi.stubEnv("VITE_STT_PROVIDER", "server");
    expect(createSttProvider()).toBeInstanceOf(ServerSttProvider);
  });

  it("respects an explicit user preference argument", () => {
    expect(createSttProvider("browser")).toBeInstanceOf(BrowserSttProvider);
    expect(createSttProvider("server")).toBeInstanceOf(ServerSttProvider);
  });
});

describe("speech error mapping", () => {
  it("maps browser errors to distinct statuses", () => {
    expect(mapSpeechError("not-allowed").status).toBe("permission_denied");
    expect(mapSpeechError("no-speech").status).toBe("empty_transcript");
    expect(mapSpeechError("network").status).toBe("network_failure");
    expect(mapSpeechError("audio-capture").status).toBe("provider_error");
    expect(mapSpeechError("timeout").status).toBe("timeout");
  });

  it("never collapses unknown errors into a generic success", () => {
    const mapped = mapSpeechError("weird-error");
    expect(mapped.status).toBe("provider_error");
    expect(mapped.status).not.toBe("success");
  });
});

describe("status metadata", () => {
  const statuses: TranscriptionStatus[] = [
    "success",
    "empty_transcript",
    "permission_denied",
    "unsupported_browser",
    "network_failure",
    "provider_error",
    "timeout",
    "parse_failed",
    "tool_failed",
    "tool_succeeded",
  ];

  it("describes every supported status", () => {
    for (const status of statuses) {
      expect(STATUS_META[status]).toBeDefined();
      expect(STATUS_META[status].label.length).toBeGreaterThan(0);
      expect(STATUS_META[status].description.length).toBeGreaterThan(0);
    }
  });

  it("marks failures correctly", () => {
    expect(STATUS_META.success.failure).toBe(false);
    expect(STATUS_META.tool_succeeded.failure).toBe(false);
    expect(STATUS_META.permission_denied.failure).toBe(true);
    expect(STATUS_META.timeout.failure).toBe(true);
  });
});
