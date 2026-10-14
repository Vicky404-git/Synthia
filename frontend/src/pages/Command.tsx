import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { LexCommandResponse, LexStatusResponse } from "../api/types";
import { MicButton } from "../components/MicButton";
import { createSttProvider, type ListenState, type SttResult, type SttSession } from "../stt";
import { useSettings } from "../state/SettingsContext";

const SESSION_KEY = "synthia.lex.session";

/** A per-browser-session id so every caller gets a distinct Lex session. */
function useLexSessionId(): string {
  return useMemo(() => {
    try {
      const existing = sessionStorage.getItem(SESSION_KEY);
      if (existing) return existing;
      const generated = `synthia-${
        globalThis.crypto?.randomUUID?.() ?? Math.random().toString(16).slice(2)
      }`;
      sessionStorage.setItem(SESSION_KEY, generated);
      return generated;
    } catch {
      return `synthia-${Math.random().toString(16).slice(2)}`;
    }
  }, []);
}

function StatusBadge({ status }: { status: LexStatusResponse }) {
  if (status.mode === "live") {
    return <span className="pill success">AWS Lex — live</span>;
  }
  if (status.mode === "simulated") {
    return <span className="pill demo">simulated (not AWS)</span>;
  }
  return <span className="pill neutral">disabled</span>;
}

function ResultCard({ result }: { result: LexCommandResponse }) {
  const slots = Object.entries(result.slots);
  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <span className="badge">{result.intent}</span>
          {result.mode === "live" ? (
            <span className="pill success">live AWS</span>
          ) : (
            <span className="pill demo">simulated</span>
          )}
        </div>
        <span className="faint" style={{ fontSize: 11 }}>
          {result.latency_ms} ms · via {result.provider}
        </span>
      </div>

      <div className="transcript-strip" style={{ marginTop: 10 }}>
        <div className="label">recognized transcript</div>
        <div className="transcript-text">{result.transcript || "—"}</div>
      </div>

      <div className="row" style={{ marginTop: 10, flexWrap: "wrap" }}>
        {slots.length === 0 ? (
          <span className="faint" style={{ fontSize: 12 }}>
            no slots detected
          </span>
        ) : (
          slots.map(([key, value]) => (
            <span key={key} className="badge">
              <strong>{key}</strong>: {value}
            </span>
          ))
        )}
      </div>

      <div className="msg-body" style={{ marginTop: 10 }}>
        {result.fulfillment_message || "(no fulfilment message)"}
      </div>

      {result.mode === "simulated" && (
        <div className="alert info" style={{ marginTop: 8 }}>
          DEMO DATA — this is a simulated command result, not a live AWS Lex
          response.
        </div>
      )}
      {result.warnings.map((warning) => (
        <div key={warning} className="alert warning" style={{ marginTop: 8 }}>
          {warning}
        </div>
      ))}
    </div>
  );
}

export function Command() {
  const { language, sttKind } = useSettings();
  const sessionId = useLexSessionId();

  const [status, setStatus] = useState<LexStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [results, setResults] = useState<LexCommandResponse[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listenState, setListenState] = useState<ListenState>("idle");
  const [livePartial, setLivePartial] = useState("");

  const sessionRef = useRef<SttSession | null>(null);
  const provider = useMemo(() => createSttProvider(sttKind), [sttKind]);

  useEffect(() => {
    api
      .lexStatus()
      .then(setStatus)
      .catch((err) =>
        setStatusError(err instanceof ApiError ? err.message : String(err)),
      );
  }, []);

  const disabled = status !== null && !status.available;

  async function send() {
    const value = text.trim();
    if (!value || sending) return;
    setSending(true);
    setError(null);
    try {
      const result = await api.lexCommand(value, sessionId);
      setResults((prev) => [result, ...prev].slice(0, 10));
      setText("");
    } catch (err) {
      setError(
        err instanceof ApiError ? `${err.code} — ${err.message}` : String(err),
      );
    } finally {
      setSending(false);
    }
  }

  function startVoice() {
    setError(null);
    setLivePartial("");
    if (!provider.available) {
      setError(provider.unsupportedReason ?? "Voice input is unavailable.");
      return;
    }
    sessionRef.current = provider.listen({
      language,
      listeners: {
        onStateChange: setListenState,
        onPartial: (value) => setLivePartial(value),
        onResult: (result: SttResult) => {
          setListenState("idle");
          setLivePartial("");
          if (result.status === "success" && result.transcript.trim()) {
            setText(result.transcript);
          } else {
            setError(result.errorMessage ?? "No usable transcript was produced.");
          }
        },
      },
    });
  }

  function stopVoice() {
    sessionRef.current?.stop();
    setListenState("idle");
  }

  const listening = listenState === "listening" || listenState === "requesting";

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 className="page-title">Voice Commands</h1>
          <p className="page-sub">
            Send a spoken or typed command to the intent recogniser. Synthia
            shows the transcript, intent, and slots it understood.
          </p>
        </div>
        {status && <StatusBadge status={status} />}
      </div>

      {statusError && (
        <div className="alert error" style={{ marginBottom: 12 }}>
          {statusError}
        </div>
      )}

      {status && (
        <div className="panel">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>recognition provider</strong>
            <StatusBadge status={status} />
          </div>
          <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>
            {status.detail}
          </div>
          {status.mode === "simulated" && (
            <div className="alert info" style={{ marginTop: 8 }}>
              A simulated provider is active. Commands are matched locally and
              clearly labelled — no AWS Lex bot is contacted.
            </div>
          )}
          {status.setup_hint && status.mode !== "live" && (
            <div className="alert warning" style={{ marginTop: 8 }}>
              {status.setup_hint}
            </div>
          )}
        </div>
      )}

      <div className="panel console-panel" style={{ marginTop: 16 }}>
        {listening && (
          <div className="alert info" style={{ marginBottom: 10 }}>
            <strong>listening…</strong>{" "}
            <span className="faint">
              {livePartial ||
                "speak your command, then press stop. Review the transcript before sending."}
            </span>
          </div>
        )}
        {listenState === "processing" && (
          <div className="alert info" style={{ marginBottom: 10 }}>
            transcribing audio…
          </div>
        )}
        <div className="composer">
          <MicButton
            state={listenState}
            disabled={sending || disabled}
            onClick={listening ? stopVoice : startVoice}
            title={listening ? "Stop listening" : "Start voice input"}
          />
          <div className="grow">
            <label className="sr-only" htmlFor="lex-input">
              Command
            </label>
            <textarea
              id="lex-input"
              className="textarea"
              rows={1}
              placeholder={
                disabled
                  ? "command provider unavailable"
                  : listening
                    ? "listening…"
                    : 'e.g. "turn on the bedroom fan" or "set the AC to 22"'
              }
              value={text}
              disabled={disabled}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={sending || disabled || !text.trim()}
            onClick={() => void send()}
          >
            {sending ? "…" : "send"}
          </button>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <span className="faint" style={{ fontSize: 11 }}>
            The recogniser only returns intent, slots, and a message. It never
            runs infrastructure operations.
          </span>
        </div>
      </div>

      {error && (
        <div className="alert error" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}

      {results.length === 0 && !error ? (
        <div className="empty" style={{ marginTop: 16 }}>
          No commands yet. Say something like “turn on the kitchen light”.
        </div>
      ) : (
        results.map((result) => <ResultCard key={result.id} result={result} />)
      )}
    </div>
  );
}
