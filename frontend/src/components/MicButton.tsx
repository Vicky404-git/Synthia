import type { ListenState } from "../stt";
import { MicIcon, StopIcon } from "./icons";

/**
 * Push-to-talk microphone button. This is always available, independent of
 * wake-word mode, and is the reliable fallback when wake word is unsupported
 * or unavailable.
 */
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
  const processing = state === "processing";
  const label = processing
    ? "Transcribing audio"
    : listening
      ? "Stop voice input"
      : "Start voice input";

  return (
    <button
      type="button"
      className={`mic ${listening ? "listening" : ""} ${processing ? "processing" : ""}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={listening}
      title={title ?? label}
    >
      {processing ? (
        <span className="mic-spinner" aria-hidden="true" />
      ) : listening ? (
        <StopIcon size={20} />
      ) : (
        <MicIcon size={20} />
      )}
    </button>
  );
}
