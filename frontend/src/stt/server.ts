import { API_BASE, getApiToken } from "../api/client";
import type { ListenOptions, SttProvider, SttSession } from "./types";

/**
 * Server-side speech-to-text provider.
 *
 * Records audio in the browser with MediaRecorder and posts it to the Synthia
 * backend, which forwards it to the configured hosted STT provider. Audio
 * leaves the device, so the UI must clearly indicate this.
 */
export class ServerSttProvider implements SttProvider {
  readonly id = "server";
  readonly label = "Hosted STT (backend)";
  readonly online = true;

  get available(): boolean {
    return (
      typeof navigator !== "undefined" &&
      Boolean(navigator.mediaDevices?.getUserMedia) &&
      typeof window !== "undefined" &&
      "MediaRecorder" in window
    );
  }

  get unsupportedReason(): string | undefined {
    if (this.available) return undefined;
    return "This browser cannot record audio (MediaRecorder unavailable).";
  }

  listen({ language, listeners, timeoutMs = 20000 }: ListenOptions): SttSession {
    let recorder: MediaRecorder | null = null;
    let stream: MediaStream | null = null;
    let stopped = false;

    const started = Date.now();
    listeners.onStateChange?.("requesting");

    const finish = (result: Parameters<NonNullable<ListenOptions["listeners"]["onResult"]>>[0]) => {
      if (stopped) return;
      stopped = true;
      listeners.onStateChange?.("idle");
      listeners.onResult(result);
    };

    const timer = window.setTimeout(() => {
      if (stopped) return;
      try {
        recorder?.stop();
      } catch {
        /* ignore */
      }
      finish({
        transcript: "",
        provider: this.id,
        language,
        status: "timeout",
        errorCode: "timeout",
        errorMessage: "Recording timed out.",
      });
    }, timeoutMs);

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((mediaStream) => {
        if (stopped) {
          mediaStream.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = mediaStream;
        const chunks: BlobPart[] = [];
        recorder = new MediaRecorder(mediaStream);
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunks.push(event.data);
        };
        recorder.onstart = () => listeners.onStateChange?.("listening");
        recorder.onstop = async () => {
          window.clearTimeout(timer);
          stream?.getTracks().forEach((track) => track.stop());
          listeners.onStateChange?.("processing");
          const blob = new Blob(chunks, {
            type: recorder?.mimeType || "audio/webm",
          });
          const form = new FormData();
          form.append("file", blob, "audio.webm");
          if (language) form.append("language", language);
          try {
            const token = getApiToken();
            const response = await fetch(`${API_BASE}/api/stt/transcribe`, {
              method: "POST",
              headers: token ? { Authorization: `Bearer ${token}` } : undefined,
              body: form,
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
              finish({
                transcript: "",
                provider: this.id,
                language,
                status: "provider_error",
                errorCode: body?.error?.code ?? "provider_error",
                errorMessage:
                  body?.error?.message ?? "The STT provider returned an error.",
              });
              return;
            }
            const text = String(body.text ?? "");
            finish({
              transcript: text,
              provider: body.provider ?? this.id,
              language: body.language ?? language,
              confidence:
                typeof body.confidence === "number" ? body.confidence : undefined,
              status: text.trim() ? "success" : "empty_transcript",
              durationMs: body.duration_ms ?? Date.now() - started,
            });
          } catch {
            finish({
              transcript: "",
              provider: this.id,
              language,
              status: "network_failure",
              errorMessage: "Could not reach the Synthia backend.",
            });
          }
        };
        recorder.start();
      })
      .catch((error: unknown) => {
        window.clearTimeout(timer);
        const name = error instanceof DOMException ? error.name : "";
        finish({
          transcript: "",
          provider: this.id,
          language,
          status:
            name === "NotAllowedError" || name === "SecurityError"
              ? "permission_denied"
              : "provider_error",
          errorCode: name || "media_error",
          errorMessage: "Microphone access failed or was denied.",
        });
      });

    return {
      stop: () => {
        try {
          if (recorder && recorder.state !== "inactive") {
            recorder.stop();
          } else {
            stream?.getTracks().forEach((track) => track.stop());
          }
        } catch {
          /* ignore */
        }
      },
    };
  }
}
