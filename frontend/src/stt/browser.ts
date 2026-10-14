import type {
  ListenOptions,
  SttProvider,
  SttResult,
  SttSession,
} from "./types";

/**
 * Return the browser's Web Speech constructor, if it exposes one.
 * Shared by the browser recogniser and the wake-word listener so both agree on
 * availability and only ever talk to the same vendor API.
 */
export function getSpeechRecognitionCtor(): SpeechRecognitionCtor | undefined {
  if (typeof window === "undefined") return undefined;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition;
}

/** Map a Web Speech API error name to one of our distinct statuses. */
export function mapSpeechError(error: string): {
  status: SttResult["status"];
  message: string;
} {
  switch (error) {
    case "not-allowed":
    case "service-not-allowed":
      return {
        status: "permission_denied",
        message: "Microphone permission was denied or blocked.",
      };
    case "no-speech":
      return { status: "empty_transcript", message: "No speech was detected." };
    case "audio-capture":
      return {
        status: "provider_error",
        message: "No microphone was found or it is unavailable.",
      };
    case "network":
      return {
        status: "network_failure",
        message: "The speech recognition network request failed.",
      };
    case "aborted":
      return { status: "empty_transcript", message: "Recognition was aborted." };
    case "timeout":
      return { status: "timeout", message: "Recognition timed out." };
    default:
      return {
        status: "provider_error",
        message: `Speech recognition error: ${error}.`,
      };
  }
}

/**
 * Browser speech recognition provider (Web Speech API).
 *
 * This is the no-setup fallback recogniser; the default provider is server-side
 * Faster-Whisper. It does not guarantee that audio stays on the device: some
 * browsers send audio to a vendor service, so the UI always warns the user that
 * online transcription may be used.
 */
export class BrowserSttProvider implements SttProvider {
  readonly id = "browser-webspeech";
  readonly label = "Browser Web Speech API";
  readonly online = true;

  private readonly ctor = getSpeechRecognitionCtor();

  get available(): boolean {
    return Boolean(this.ctor);
  }

  get unsupportedReason(): string | undefined {
    if (this.ctor) return undefined;
    return (
      "This browser does not expose the Web Speech API. Use typed input, or a " +
      "Chromium-based browser over HTTPS."
    );
  }

  listen({ language, listeners, timeoutMs = 15000 }: ListenOptions): SttSession {
    if (!this.ctor) {
      listeners.onResult({
        transcript: "",
        provider: this.id,
        status: "unsupported_browser",
        errorMessage: this.unsupportedReason,
      });
      return { stop: () => undefined };
    }

    const recognition = new this.ctor();
    recognition.lang = language;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    let delivered = false;
    let finalText = "";
    let confidence: number | undefined;
    const started = Date.now();

    const timer = window.setTimeout(() => {
      if (delivered) return;
      try {
        recognition.stop();
      } catch {
        /* ignore */
      }
      delivered = true;
      listeners.onStateChange?.("idle");
      listeners.onResult({
        transcript: finalText,
        provider: this.id,
        language,
        status: "timeout",
        errorCode: "timeout",
        errorMessage: "No final transcript was received in time.",
        durationMs: Date.now() - started,
      });
    }, timeoutMs);

    const cleanup = () => {
      window.clearTimeout(timer);
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      recognition.onstart = null;
    };

    recognition.onstart = () => listeners.onStateChange?.("listening");

    recognition.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const alternative = result[0];
        if (result.isFinal) {
          finalText += alternative.transcript;
          if (alternative.confidence > 0) {
            confidence = alternative.confidence;
          }
        } else {
          interim += alternative.transcript;
        }
      }
      listeners.onPartial?.(finalText + interim, Boolean(finalText));
    };

    recognition.onerror = (event) => {
      if (delivered) return;
      delivered = true;
      clearTimeout(timer);
      const mapped = mapSpeechError(event.error);
      listeners.onStateChange?.("idle");
      listeners.onResult({
        transcript: finalText,
        provider: this.id,
        language,
        status: mapped.status,
        errorCode: event.error,
        errorMessage: mapped.message,
        durationMs: Date.now() - started,
      });
    };

    recognition.onend = () => {
      cleanup();
      if (delivered) return;
      delivered = true;
      const text = finalText.trim();
      listeners.onStateChange?.("idle");
      listeners.onResult({
        transcript: finalText,
        provider: this.id,
        language,
        confidence,
        status: text ? "success" : "empty_transcript",
        durationMs: Date.now() - started,
      });
    };

    try {
      listeners.onStateChange?.("requesting");
      recognition.start();
    } catch (error) {
      cleanup();
      delivered = true;
      listeners.onStateChange?.("idle");
      listeners.onResult({
        transcript: "",
        provider: this.id,
        language,
        status: "provider_error",
        errorMessage:
          error instanceof Error ? error.message : "Could not start recognition.",
      });
    }

    return {
      stop: () => {
        try {
          recognition.stop();
        } catch {
          /* ignore */
        }
      },
    };
  }
}
