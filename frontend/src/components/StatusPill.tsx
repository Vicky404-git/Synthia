import type { ProviderInfo, TranscriptionStatus } from "../api/types";
import { STATUS_META } from "../history/status";

export function StatusPill({
  tone,
  children,
}: {
  tone: "success" | "warning" | "error" | "neutral" | "demo";
  children: React.ReactNode;
}) {
  return (
    <span className={`pill ${tone}`}>
      <span className="dot" aria-hidden="true" />
      {children}
    </span>
  );
}

export function ProviderPill({ provider }: { provider: ProviderInfo }) {
  const tone =
    provider.status === "connected"
      ? "success"
      : provider.status === "demo"
        ? "demo"
        : provider.status === "error"
          ? "error"
          : provider.status === "unconfigured"
            ? "warning"
            : "neutral";
  return <StatusPill tone={tone}>{provider.label}: {provider.status}</StatusPill>;
}

export function TranscriptionPill({ status }: { status: TranscriptionStatus }) {
  const meta = STATUS_META[status];
  const tone =
    meta.tone === "success" ? "success" : meta.tone === "error" ? "error" : meta.tone === "warning" ? "warning" : "neutral";
  return <StatusPill tone={tone}>{meta.label}</StatusPill>;
}
