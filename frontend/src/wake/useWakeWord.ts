import { useEffect, useMemo, useRef, useState } from "react";
import { getSpeechRecognitionCtor } from "../stt/browser";
import { DEFAULT_WAKE_PHRASE, matchesWakePhrase } from "./phrase";

/**
 * Wake-word detection state, as shown to the user.
 *
 * - `off`         — the user has not enabled wake-word mode.
 * - `unsupported` — the browser does not expose the Web Speech API.
 * - `waiting`     — listening in the background for the wake phrase.
 * - `detected`    — the wake phrase was heard; the request recorder is starting.
 * - `error`       — listening stopped and needs the user to act (permission etc.).
 */
export type WakeStatus = "off" | "unsupported" | "waiting" | "detected" | "error";

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

const RESTART_DELAY_MS = 400;

/**
 * Background wake-word listener built on the browser Web Speech API.
 *
 * This only performs *keyword spotting*. Real transcription always goes through
 * the configured STT provider (server-side Faster-Whisper by default). The Web
 * Speech API may send microphone audio to the browser vendor, so this is an
 * explicit, opt-in feature rather than the default input path.
 *
 * The hook owns at most one recognition session. It releases the microphone
 * (stops the session) the moment the wake phrase is heard or while the request
 * recorder is active (`paused`), so the detector and recorder never compete.
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
    // Set after a fatal error (permission, no device) to stop restart loops.
    let halted = false;

    setError(null);

    const start = () => {
      if (cancelled || halted) return;
      setStatus("waiting");
      recognition = new ctor();
      recognition.lang = language;
      // continuous + interimResults lets us spot the word inside a sentence.
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onresult = (event) => {
        let heard = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          heard += event.results[i][0].transcript;
        }
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
            halted = true;
            setStatus("error");
            setError("Microphone permission for wake-word listening was denied.");
            break;
          case "audio-capture":
            halted = true;
            setStatus("error");
            setError("No microphone was found for wake-word listening.");
            break;
          case "network":
            halted = true;
            setStatus("error");
            setError("Wake-word listening lost its network connection.");
            break;
          case "no-speech":
          case "aborted":
            // Harmless: onend will quietly restart the session.
            break;
          default:
            halted = true;
            setStatus("error");
            setError(`Wake-word listener error: ${event.error}.`);
        }
      };

      recognition.onend = () => {
        if (cancelled || intentionalStop || halted) return;
        // The engine stops on its own after silence; re-arm after a short,
        // fixed delay so we never spin in a tight restart loop.
        restartTimer = window.setTimeout(start, RESTART_DELAY_MS);
      };

      try {
        recognition.start();
      } catch {
        halted = true;
        setStatus("error");
        setError("Could not start wake-word listening.");
      }
    };

    start();

    // Cleanup on disable, pause, unmount or dependency change: drop handlers
    // first, then abort, so no stale callbacks can fire or leak.
    return () => {
      cancelled = true;
      intentionalStop = true;
      if (restartTimer !== null) window.clearTimeout(restartTimer);
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
