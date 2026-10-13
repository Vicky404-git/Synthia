import type { TranscriptionStatus } from "../api/types";

export type StatusTone = "success" | "warning" | "error" | "neutral";

export interface StatusMeta {
  label: string;
  tone: StatusTone;
  description: string;
  failure: boolean;
}

export const STATUS_META: Record<TranscriptionStatus, StatusMeta> = {
  success: {
    label: "Transcribed",
    tone: "success",
    description: "Speech was recognised successfully.",
    failure: false,
  },
  tool_succeeded: {
    label: "Tool succeeded",
    tone: "success",
    description: "The routed cloud tool completed successfully.",
    failure: false,
  },
  empty_transcript: {
    label: "Empty transcript",
    tone: "warning",
    description: "No speech was detected or the transcript was blank.",
    failure: true,
  },
  permission_denied: {
    label: "Permission denied",
    tone: "error",
    description: "Microphone permission was denied or blocked.",
    failure: true,
  },
  unsupported_browser: {
    label: "Unsupported browser",
    tone: "warning",
    description: "This browser cannot perform speech recognition.",
    failure: true,
  },
  network_failure: {
    label: "Network failure",
    tone: "error",
    description: "A network request failed (recognition or backend).",
    failure: true,
  },
  provider_error: {
    label: "Provider error",
    tone: "error",
    description: "The speech or cloud provider returned an error.",
    failure: true,
  },
  timeout: {
    label: "Timeout",
    tone: "warning",
    description: "No final result arrived before the timeout.",
    failure: true,
  },
  parse_failed: {
    label: "Intent parse failed",
    tone: "warning",
    description: "A transcript was received but intent parsing failed.",
    failure: true,
  },
  tool_failed: {
    label: "Tool failed",
    tone: "error",
    description: "The routed tool failed to execute.",
    failure: true,
  },
};

export function isFailure(status: TranscriptionStatus): boolean {
  return STATUS_META[status]?.failure ?? true;
}
