import { useEffect, useMemo, useRef, useState } from "react";
import { getSpeechRecognitionCtor } from "../stt/browser";
import { DEFAULT_WAKE_PHRASE, matchesWakePhrase } from "./phrase";

/**
 * Wake-word detection state, as shown to the user.
 *
 * - `off`         — the user has not enabled wake-word mode.
 * - `unsupported` — the browser does not expose the Web Speech API.
 * - `waiting`     — listening in the background for the wake phrase.
 * - `recovering`  — listening dropped out (network/engine) and is re-arming.
 * - `detected`    — the wake phrase was heard; the request recorder is starting.
 * - `error`       — listening stopped and needs the user to act (permission etc.).
 */
export type WakeStatus =
  | "off"
  | "unsupported"
  | "waiting"
  | "recovering"
  | "detected"
  | "error";

export interface UseWakeWordOptions {
  /** The user's saved preference. OFF unless they explicitly turn it on. */
  enabled: boolean;
  /** True while the request recorder owns the microphone; detection pauses. */
  paused: boolean;
  /** BCP-47 locale used for keyword spotting only. */
  language: string;
  /** Wake phrase. Defaults to "synthia". */
  phrase?: string;
  /** Called once per detected wake phrase, with the microphone already released. */
  onWake: () => void;
}

export interface UseWakeWordResult {
  status: WakeStatus;
  supported: boolean;
  unsupportedReason?: string;
  error: string | null;
}

// A short, fixed delay used for the normal "engine stopped after silence" case.
const RESTART_DELAY_MS = 400;
// Bounded exponential backoff for recoverable connection failures.
const RETRY_BASE_DELAY_MS = 1000;
const RETRY_MAX_DELAY_MS = 30000;

function backoffDelay(attempt: number): number {
  const step = RETRY_BASE_DELAY_MS * 2 ** Math.max(0, attempt - 1);
  return Math.min(step, RETRY_MAX_DELAY_MS);
}

/**
 * Background wake-word listener built on the browser Web Speech API.
 *
 * This only performs *keyword spotting*. Real transcription always goes through
 * the configured STT provider (server-side Faster-Whisper by default). The Web
 * Speech API may send microphone audio to the browser vendor, so this is an
 * explicit, opt-in feature rather than the default input path. It is therefore
 * not a guaranteed-offline feature.
 *
 * The hook owns at most one recognition session. It releases the microphone
 * (stops the session) the moment the wake phrase is heard or while the request
 * recorder is active (`paused`), so the detector and recorder never compete.
 *
 * Failure handling is deliberately split by cause:
 * - permission denial / no audio device are fatal and ask the user to act;
 * - transient network/engine failures re-arm with a bounded exponential backoff
 *   (never a tight restart loop), and while the device is offline the listener
 *   waits for the `online` event instead of hammering the service.
 */
export function useWakeWord({
  enabled,
  paused,
  language,
  phrase = DEFAULT_WAKE_PHRASE,
  onWake,
}: UseWakeWordOptions): UseWakeWordResult {
  const ctor = useMemo(() => getSpeechRecognitionCtor(), []);
  const supported = Boolean(ctor);
  const [status, setStatus] = useState<WakeStatus>(enabled ? "waiting" : "off");
  const [error, setError] = useState<string | null>(null);

  // Keep the latest callback in a ref so the recognition effect does not need
  // to restart every time the parent re-renders and passes a new closure.
  const onWakeRef = useRef(onWake);
  useEffect(() => {
    onWakeRef.current = onWake;
  }, [onWake]);

  useEffect(() => {
    if (!enabled) {
      setStatus("off");
      setError(null);
      return;
    }
    if (!supported || !ctor) {
      setStatus("unsupported");
      return;
    }
    // While the request recorder is recording, do not hold a second session.
    if (paused) {
      return;
    }

    let cancelled = false;
    let recognition: SpeechRecognition | null = null;
    let restartTimer: number | null = null;
    // Set when *we* stop the session, so onend does not auto-restart it.
    let intentionalStop = false;
    // Set after a fatal error (permission, no device) to stop all restarts.
    let halted = false;
    // Set while the device is offline; we wait for `online` instead of retrying.
    let waitingForNetwork = false;
    // Consecutive recoverable failures, used to grow the backoff delay.
    let attempt = 0;

    setError(null);

    const clearTimer = () => {
      if (restartTimer !== null) {
        window.clearTimeout(restartTimer);
        restartTimer = null;
      }
    };

    const scheduleRestart = (delay: number) => {
      if (cancelled || halted) return;
      clearTimer();
      restartTimer = window.setTimeout(() => {
        restartTimer = null;
        start();
      }, delay);
    };

    const start = () => {
      if (cancelled || halted) return;
      // Tear down any previous session before creating a new one so no stale
      // handlers survive across a restart.
      if (recognition) {
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        recognition.onstart = null;
        try {
          recognition.abort();
        } catch {
          /* already stopped */
        }
        recognition = null;
      }
      setStatus("waiting");
      setError(null);
      recognition = new ctor();
      recognition.lang = language;
      // continuous + interimResults lets us spot the word inside a sentence.
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        // Deliberately do NOT reset the backoff counter here: onstart fires as
        // soon as the engine connects and can be followed immediately by a
        // network error. The counter is reset only when a session provably
        // works (a result), ends cleanly, or the network returns, so repeated
        // connect -> network-failure cycles back off progressively.
        setStatus("waiting");
      };

      recognition.onresult = (event) => {
        let heard = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          heard += event.results[i][0].transcript;
        }
        // Receiving any transcript proves the service is reachable again.
        attempt = 0;
        waitingForNetwork = false;
        if (!matchesWakePhrase(heard, phrase)) return;
        // Release the microphone before the parent starts recording.
        intentionalStop = true;
        try {
          recognition?.stop();
        } catch {
          /* already stopped */
        }
        setStatus("detected");
        onWakeRef.current();
        // If the parent starts recording it will set `paused`, and the effect
        // cleanup below will cancel this timer. Otherwise (for example the
        // recorder could not start) we re-arm so listening is never silently
        // left off.
        restartTimer = window.setTimeout(() => {
          intentionalStop = false;
          start();
        }, RESTART_DELAY_MS);
      };

      recognition.onerror = (event) => {
        switch (event.error) {
          case "not-allowed":
          case "service-not-allowed":
            // Fatal: the user must grant permission; do not retry in a loop.
            halted = true;
            clearTimer();
            setStatus("error");
            setError("Microphone permission for wake-word listening was denied.");
            break;
          case "audio-capture":
            // Fatal for now: there is no usable microphone.
            halted = true;
            clearTimer();
            setStatus("error");
            setError("No microphone was found for wake-word listening.");
            break;
          case "network":
            attempt += 1;
            if (typeof navigator !== "undefined" && navigator.onLine === false) {
              waitingForNetwork = true;
              clearTimer();
              setStatus("recovering");
              setError(
                "Wake-word listening is paused until the network comes back.",
              );
            } else {
              setStatus("recovering");
              setError(
                "Wake-word listening lost its network connection. Reconnecting…",
              );
              scheduleRestart(backoffDelay(attempt));
            }
            break;
          case "no-speech":
          case "aborted":
            // Harmless: onend will quietly restart the session.
            break;
          default:
            // Treat anything else as transient and back off rather than stopping
            // permanently on the first hiccup.
            attempt += 1;
            setStatus("recovering");
            setError(`Wake-word listener error: ${event.error}. Reconnecting…`);
            scheduleRestart(backoffDelay(attempt));
        }
      };

      recognition.onend = () => {
        if (cancelled || intentionalStop || halted || waitingForNetwork) return;
        // If a restart is already scheduled (e.g. after a backoff), let it run.
        if (restartTimer !== null) return;
        // A clean end (no error) means the connection is healthy again; clear
        // any accumulated backoff, then re-arm after a short fixed delay so we
        // never spin in a tight restart loop.
        attempt = 0;
        scheduleRestart(RESTART_DELAY_MS);
      };

      try {
        recognition.start();
      } catch {
        // Starting can fail transiently (e.g. the engine is still shutting
        // down). Back off instead of stopping permanently.
        attempt += 1;
        setStatus("recovering");
        setError("Could not start wake-word listening. Retrying…");
        scheduleRestart(backoffDelay(attempt));
      }
    };

    const handleOnline = () => {
      if (cancelled || halted || !waitingForNetwork) return;
      waitingForNetwork = false;
      attempt = 0;
      scheduleRestart(RESTART_DELAY_MS);
    };
    window.addEventListener("online", handleOnline);

    start();

    // Cleanup on disable, pause, unmount or dependency change: drop handlers
    // first, then abort, so no stale callbacks can fire or leak.
    return () => {
      cancelled = true;
      intentionalStop = true;
      window.removeEventListener("online", handleOnline);
      clearTimer();
      if (recognition) {
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        recognition.onstart = null;
        try {
          recognition.abort();
        } catch {
          /* ignore */
        }
      }
      // Best-effort cleanup for any audio resources that may be held
      try {
        const maybeStream = (recognition as any)?.stream;
        if (maybeStream && typeof maybeStream.getTracks === "function") {
          maybeStream.getTracks().forEach((track: MediaStreamTrack) => {
            try {
              track.stop();
            } catch {
              /* ignore */
            }
          });
        }
      } catch {
        /* ignore */
      }
      try {
        const maybeCtx = (recognition as any)?.audioContext as AudioContext | undefined;
        if (maybeCtx && typeof maybeCtx.close === "function") {
          const closePromise = maybeCtx.close();
          if (closePromise && typeof (closePromise as any).catch === "function") {
            (closePromise as any).catch(() => {});
          }
        }
      } catch {
        /* ignore */
      }
    };
  }, [enabled, paused, supported, ctor, language, phrase]);

  return {
    status,
    supported,
    unsupportedReason: supported
      ? undefined
      : "This browser does not expose the Web Speech API, so wake-word mode " +
        "is unavailable. Use the microphone button or typed input instead.",
    error,
  };
}
