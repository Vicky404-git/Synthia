export type Mode = "general" | "cloud";

export type OperationClass =
  | "conversation"
  | "explanation"
  | "read_only"
  | "mutating";

export type TranscriptionStatus =
  | "success"
  | "empty_transcript"
  | "permission_denied"
  | "unsupported_browser"
  | "network_failure"
  | "provider_error"
  | "timeout"
  | "parse_failed"
  | "tool_failed"
  | "tool_succeeded";

export type InputSource = "speech" | "typed";

export interface ToolCall {
  name: string;
  provider: string;
  read_only: boolean;
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  requires_confirmation: boolean;
  simulated: boolean;
}

export interface ChatResponse {
  id: string;
  timestamp: string;
  mode: Mode;
  operation: OperationClass;
  reply: string;
  transcript: string;
  provider_used: string;
  tool_call: ToolCall | null;
  usage: Record<string, unknown> | null;
  warnings: string[];
}

export interface ToolInfo {
  name: string;
  description: string;
  provider: string;
  read_only: boolean;
  required_permissions: string[];
  parameters: Record<string, unknown>;
  available: boolean;
  unavailable_reason: string | null;
}

export interface ProviderInfo {
  id: string;
  label: string;
  status: "connected" | "unconfigured" | "error" | "demo" | "disabled";
  read_only: boolean;
  detail: string;
  capabilities: string[];
  setup_hint: string | null;
}

export interface ProviderListResponse {
  mode: string;
  providers: ProviderInfo[];
}

export interface ToolListResponse {
  tools: ToolInfo[];
  count: number;
}

export interface ToolExecuteResponse {
  name: string;
  provider: string;
  read_only: boolean;
  simulated: boolean;
  requires_confirmation: boolean;
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  message: string;
}

export interface DependencyStatus {
  name: string;
  ready: boolean;
  detail: string;
}

export interface ReadyResponse {
  ready: boolean;
  service: string;
  version: string;
  environment: string;
  demo_mode: boolean;
  dependencies: DependencyStatus[];
  timestamp: string;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  timestamp: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}
