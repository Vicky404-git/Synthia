import { PowerIcon } from "./icons";

/**
 * The single status surface for wake-word mode. It combines the wake
 * detector's state with the recording lifecycle so the user always knows
 * whether the microphone is live and what Synthia is doing.
 */
export type WakeUiStatus =
  | "disabled"
  | "unsupported"
  | "waiting"
  | "detected"
  | "recording"
  | "processing"
  | "error";

const LABELS: Record<WakeUiStatus, string> = {
  disabled: "wake word off",
  unsupported: "wake word unavailable in this browser",
  waiting: "armed — say “synthia”",
  detected: "wake word detected",
  recording: "microphone live — recording your request",
  processing: "microphone released — transcribing",
  error: "wake word stopped",
};

export function WakeStatusBar({
  status,
  message,
  onDisable,
}: {
  status: WakeUiStatus;
  /** Extra explanation, e.g. a permission error. */
  message?: string;
  onDisable: () => void;
}) {
  return (
    <div className={`wake-bar ${status}`} role="status" aria-live="polite">
      <span className="wake-light" aria-hidden="true" />
      <div className="wake-text">
        <span className="wake-label">{LABELS[status]}</span>
        {message && <span className="wake-detail">{message}</span>}
      </div>
      <button
        type="button"
        className="btn btn-sm btn-ghost wake-off"
        onClick={onDisable}
        title="Turn off wake-word listening and stop the microphone"
      >
        <PowerIcon size={14} />
        turn off
      </button>
    </div>
  );
}
