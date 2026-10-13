import type { TranscriptionStatus } from "../api/types";

export type ListenState = "idle" | "requesting" | "listening" | "processing";

export interface SttResult {
  transcript: string;
  provider: string;
  language?: string;
  /** Only present when the provider genuinely returns a confidence score. */
  confidence?: number;
  status: TranscriptionStatus;
  errorCode?: string;
  errorMessage?: string;
  durationMs?: number;
}

export interface SttListeners {
  onPartial?: (text: string, isFinal: boolean) => void;
  onResult: (result: SttResult) => void;
  onStateChange?: (state: ListenState) => void;
}

export interface ListenOptions {
  language: string;
  listeners: SttListeners;
  /** Milliseconds without a final result before giving up. */
  timeoutMs?: number;
}

export interface SttSession {
  stop: () => void;
}

export interface SttProvider {
  readonly id: string;
  readonly label: string;
  readonly available: boolean;
  readonly unsupportedReason?: string;
  readonly online: boolean;
  listen: (options: ListenOptions) => SttSession;
}
