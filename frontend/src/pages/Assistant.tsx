import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { streamChat, type ChatHistoryMessage } from "../api/client";
import type { Mode, OperationClass, ToolCall, TranscriptionStatus } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { MicButton } from "../components/MicButton";
import { ToolCallView } from "../components/ToolCallView";
import {
  WakeStatusBar,
  type WakeUiStatus,
} from "../components/WakeStatusBar";
import { createSttProvider, type ListenState, type SttResult, type SttSession } from "../stt";
import { useWakeWord } from "../wake";
import { useHistory } from "../state/HistoryContext";
import { useSettings } from "../state/SettingsContext";
import { newEventId, type HistoryEvent } from "../history/store";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  transcript?: string;
  operation?: OperationClass;
  providerUsed?: string;
  toolCall?: ToolCall | null;
  warnings?: string[];
  error?: { code: string; message: string };
  pending?: boolean;
}

function statusForError(code: string): TranscriptionStatus {
  switch (code) {
    case "network_failure":
      return "network_failure";
    case "timeout":
      return "timeout";
    case "rate_limited":
    case "provider_error":
      return "provider_error";
    case "unknown_tool":
    case "invalid_tool_arguments":
    case "permission_denied":
    case "provider_not_configured":
      return "tool_failed";
    default:
      return "provider_error";
  }
}

export function Assistant() {
  const { language, sttKind, wakeWordEnabled, setWakeWordEnabled } = useSettings();
  const { add: addHistory, update: updateHistory } = useHistory();
  const location = useLocation();

  const [mode, setMode] = useState<Mode>("general");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [listenState, setListenState] = useState<ListenState>("idle");
  const [livePartial, setLivePartial] = useState("");
  const [pendingTranscript, setPendingTranscript] = useState<{
    text: string;
    provider: string;
    eventId: string;
  } | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [banner, setBanner] = useState<{ tone: string; text: string } | null>(null);
  const [confirming, setConfirming] = useState<{
    text: string;
    source: "speech" | "typed";
    eventId: string;
  } | null>(null);

  const sessionRef = useRef<SttSession | null>(null);
  const provider = useMemo(() => createSttProvider(sttKind), [sttKind]);

  // Wake-word listening is an optional convenience layered on top of the
  // manual recorder. It is paused while the recorder owns the microphone (so
  // the two never compete) and re-armed once recording finishes.
  const recording = listenState !== "idle";
  const wake = useWakeWord({
    enabled: wakeWordEnabled,
    paused: recording,
    language,
    onWake: startVoice,
  });

  // Single combined status for the wake/record lifecycle.
  const wakeUi: WakeUiStatus = !wakeWordEnabled
    ? "disabled"
    : wake.status === "unsupported"
      ? "unsupported"
      : wake.status === "error"
        ? "error"
        : listenState === "processing"
          ? "processing"
          : listenState === "listening" || listenState === "requesting"
            ? "recording"
            : wake.status === "detected"
              ? "detected"
              : "waiting";

  // Prefill from the History page ("send to assistant" / retry).
  useEffect(() => {
    const state = location.state as { prefill?: string; mode?: Mode } | null;
    if (state?.prefill) {
      setInput(state.prefill);
      if (state.mode) setMode(state.mode);
      setBanner({
        tone: "info",
        text: "Transcript loaded from history. Review and edit before sending.",
      });
      window.history.replaceState({}, "");
    }
  }, [location.state]);

  function pushMessage(message: Message) {
    setMessages((prev) => [...prev, message]);
  }

  function finalizeAssistant(id: string, patch: Partial<Message>) {
    setMessages((prev) =>
      prev.map((message) => (message.id === id ? { ...message, ...patch } : message)),
    );
  }

  function startVoice() {
    setBanner(null);
    setLivePartial("");
    if (!provider.available) {
      const event: HistoryEvent = {
        event_id: newEventId(),
        timestamp: new Date().toISOString(),
        transcript: "",
        provider: provider.id,
        source: "speech",
        status: "unsupported_browser",
        error: { code: "unsupported_browser", message: provider.unsupportedReason ?? "" },
        local_only: true,
      };
      addHistory(event);
      setBanner({ tone: "warning", text: provider.unsupportedReason ?? "Unsupported." });
      return;
    }
    sessionRef.current = provider.listen({
      language,
      listeners: {
        onStateChange: setListenState,
        onPartial: (text) => setLivePartial(text),
        onResult: handleSpeechResult,
      },
    });
  }

  function stopVoice() {
    sessionRef.current?.stop();
    setListenState("idle");
  }

  // Turning wake mode off also stops any recording that is currently running,
  // so the microphone is never left live after the user opts out.
  function disableWakeWord() {
    setWakeWordEnabled(false);
    stopVoice();
  }

  function handleSpeechResult(result: SttResult) {
    setListenState("idle");
    setLivePartial("");
    const event: HistoryEvent = {
      event_id: newEventId(),
      timestamp: new Date().toISOString(),
      transcript: result.transcript,
      provider: result.provider,
      language: result.language,
      source: "speech",
      status: result.status,
      confidence: result.confidence,
      duration_ms: result.durationMs,
      error: result.errorMessage
        ? { code: result.errorCode ?? result.status, message: result.errorMessage }
        : null,
      local_only: true,
    };
    addHistory(event);

    if (result.status === "success" && result.transcript.trim()) {
      setPendingTranscript({
        text: result.transcript,
        provider: result.provider,
        eventId: event.event_id,
      });
      setInput(result.transcript);
    } else {
      setBanner({
        tone: "warning",
        text: result.errorMessage ?? "No usable transcript was produced.",
      });
    }
  }

  async function runChat(opts: {
    text: string;
    source: "speech" | "typed";
    eventId: string;
    confirmed: boolean;
  }) {
    const text = opts.text.trim();
    if (!text || streaming) return;

    const history: ChatHistoryMessage[] = messages
      .filter((message) => !message.pending)
      .map((message) => ({ role: message.role, content: message.text }));

    pushMessage({
      id: newEventId(),
      role: "user",
      text,
      transcript: opts.source === "speech" ? text : undefined,
    });

    const assistantId = newEventId();
    pushMessage({ id: assistantId, role: "assistant", text: "", pending: true });
    setStreaming(true);
    setInput("");
    setPendingTranscript(null);
    setBanner(null);

    await streamChat(
      { message: text, mode, history, confirmed: opts.confirmed },
      {
        onToken: (token) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, text: message.text + token }
                : message,
            ),
          );
        },
        onResult: (response) => {
          finalizeAssistant(assistantId, {
            text: response.reply,
            operation: response.operation,
            providerUsed: response.provider_used,
            toolCall: response.tool_call,
            warnings: response.warnings,
            pending: false,
          });
          updateHistory(opts.eventId, {
            parsed_intent: response.operation,
            tool_name: response.tool_call?.name ?? null,
            tool_status: response.tool_call ? "tool_succeeded" : null,
            reply: response.reply,
          });
        },
        onError: (error) => {
          if (error.code === "confirmation_required") {
            setMessages((prev) => prev.filter((message) => message.id !== assistantId));
            setConfirming({ text, source: opts.source, eventId: opts.eventId });
            setStreaming(false);
            return;
          }
          finalizeAssistant(assistantId, {
            text: error.message,
            error: { code: error.code, message: error.message },
            pending: false,
          });
          updateHistory(opts.eventId, {
            status: statusForError(error.code),
            error: { code: error.code, message: error.message },
            tool_name: null,
          });
          if (error.code === "unauthorized") {
            setBanner({
              tone: "error",
              text: "This operation requires an API token. Set VITE_API_TOKEN or configure the backend.",
            });
          }
        },
        onDone: () => setStreaming(false),
      },
    );
  }

  function sendTyped() {
    const text = input.trim();
    if (!text) return;
    const eventId = newEventId();
    addHistory({
      event_id: eventId,
      timestamp: new Date().toISOString(),
      transcript: text,
      provider: "typed",
      source: "typed",
      status: "success",
      local_only: true,
    });
    void runChat({ text, source: "typed", eventId, confirmed: false });
  }

  function sendPendingTranscript() {
    if (!pendingTranscript) return;
    const text = input.trim() || pendingTranscript.text;
    void runChat({
      text,
      source: "speech",
      eventId: pendingTranscript.eventId,
      confirmed: false,
    });
  }

  function discardPending() {
    setPendingTranscript(null);
    setInput("");
  }

  function confirmMutation() {
    if (!confirming) return;
    const { text, source, eventId } = confirming;
    setConfirming(null);
    void runChat({ text, source, eventId, confirmed: true });
  }

  const listening = listenState === "listening" || listenState === "requesting";

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 className="page-title">Assistant</h1>
          <p className="page-sub">
            Ask general questions or manage cloud resources in natural language.
          </p>
        </div>
        <div className="segmented" role="tablist" aria-label="Conversation mode">
          <button
            type="button"
            className={mode === "general" ? "active" : ""}
            onClick={() => setMode("general")}
          >
            general
          </button>
          <button
            type="button"
            className={mode === "cloud" ? "active" : ""}
            onClick={() => setMode("cloud")}
          >
            cloud
          </button>
        </div>
      </div>

      {banner && (
        <div className={`alert ${banner.tone}`} style={{ marginBottom: 12 }}>
          {banner.text}
        </div>
      )}

      <div className="chat-log">
        {messages.length === 0 && (
          <div className="empty">
            {mode === "cloud"
              ? 'Try: "list my EC2 instances" or "which containers are running?"'
              : 'Try: "explain the difference between EC2 and a container"'}
          </div>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`msg ${message.role === "user" ? "msg-user" : "msg-assistant"}`}
          >
            <div className="msg-meta">
              <strong>{message.role === "user" ? "you" : "synthia"}</strong>
              {message.operation && <span className="badge">{message.operation}</span>}
              {message.providerUsed && (
                <span className="faint">via {message.providerUsed}</span>
              )}
              {message.pending && <span className="pill neutral">…</span>}
            </div>
            {message.transcript && (
              <div className="transcript-strip">
                <div className="label">recognized transcript</div>
                <div className="transcript-text">{message.transcript}</div>
              </div>
            )}
            <div className="msg-body">{message.text || (message.pending ? "…" : "")}</div>
            {message.error && (
              <div className="alert error" style={{ marginTop: 8 }}>
                <strong>{message.error.code}</strong> — {message.error.message}
              </div>
            )}
            {message.warnings?.map((warning) => (
              <div key={warning} className="alert warning" style={{ marginTop: 8 }}>
                {warning}
              </div>
            ))}
            {message.toolCall && <ToolCallView call={message.toolCall} />}
          </div>
        ))}
      </div>

      <div className="panel console-panel" style={{ marginTop: 16, position: "sticky", bottom: 8 }}>
        {wakeWordEnabled && (
          <WakeStatusBar
            status={wakeUi}
            message={
              wake.error ??
              (wake.status === "unsupported" ? wake.unsupportedReason : undefined)
            }
            onDisable={disableWakeWord}
          />
        )}
        {listening && (
          <div className="alert info" style={{ marginBottom: 10 }}>
            <strong>listening…</strong>{" "}
            <span className="faint">
              {livePartial ||
                (sttKind === "server"
                  ? "speak now. audio is uploaded to the backend for transcription."
                  : "speak now. the browser may send audio to a vendor service.")}
            </span>
          </div>
        )}
        {listenState === "processing" && (
          <div className="alert info" style={{ marginBottom: 10 }}>
            {sttKind === "server"
              ? "processing audio on the backend…"
              : "processing audio…"}
          </div>
        )}
        {pendingTranscript && (
          <div className="transcript-strip" style={{ marginBottom: 10 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <div className="label">
                  recognized transcript — review before sending
                </div>
                <div className="transcript-text">{pendingTranscript.text}</div>
                <div className="faint" style={{ fontSize: 11 }}>
                  provider: {pendingTranscript.provider}
                </div>
              </div>
              <div className="row">
                <button type="button" className="btn btn-sm" onClick={sendPendingTranscript}>
                  send
                </button>
                <button type="button" className="btn btn-sm btn-ghost" onClick={discardPending}>
                  discard
                </button>
              </div>
            </div>
          </div>
        )}
        <div className="composer">
          <MicButton
            state={listenState}
            disabled={streaming}
            onClick={listening ? stopVoice : startVoice}
            title={listening ? "Stop listening" : "Start voice input"}
          />
          <div className="grow">
            <label className="sr-only" htmlFor="composer-input">
              Message
            </label>
            <textarea
              id="composer-input"
              className="textarea"
              rows={1}
              placeholder={
                listening ? "listening…" : "type a command, or use the microphone"
              }
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (pendingTranscript) sendPendingTranscript();
                  else sendTyped();
                }
              }}
            />
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={streaming || !input.trim()}
            onClick={pendingTranscript ? sendPendingTranscript : sendTyped}
          >
            {streaming ? "…" : "send"}
          </button>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <span className="faint" style={{ fontSize: 11 }}>
            {mode === "cloud"
              ? "cloud mode: read-only tools; mutating actions require confirmation."
              : "general mode: no infrastructure tools are executed."}
          </span>
          <div className="spacer" />
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => {
              setMessages([]);
              setPendingTranscript(null);
              setInput("");
            }}
          >
            new conversation
          </button>
        </div>
      </div>

      {confirming && (
        <ConfirmDialog
          title="Confirm mutating operation"
          confirmLabel="Execute"
          onCancel={() => setConfirming(null)}
          onConfirm={confirmMutation}
        >
          <p>
            Synthia routed your request to a <strong>mutating</strong> tool. This
            demonstration only supports a labelled simulated action; no real
            infrastructure will be changed.
          </p>
          <pre className="mono-block">{confirming.text}</pre>
        </ConfirmDialog>
      )}
    </div>
  );
}
