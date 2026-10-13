import type { ListenState } from "../stt";

export function MicButton({
  state,
  disabled,
  onClick,
  title,
}: {
  state: ListenState;
  disabled?: boolean;
  onClick: () => void;
  title?: string;
}) {
  const listening = state === "listening" || state === "requesting";
  const glyph =
    state === "processing" ? "…" : listening ? "■" : "🎤";
  return (
    <button
      type="button"
      className={`mic ${listening ? "listening" : ""}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={listening ? "Stop listening" : "Start voice input"}
      title={title ?? (listening ? "Stop listening" : "Start voice input")}
    >
      <span aria-hidden="true">{glyph}</span>
    </button>
  );
}
