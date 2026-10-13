import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Mode } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { TranscriptionPill } from "../components/StatusPill";
import { STATUS_META } from "../history/status";
import { filterHistory, type HistoryEvent } from "../history/store";
import { useHistory } from "../state/HistoryContext";

type Filter = "all" | "success" | "failed";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function History() {
  const { events, remove, clear } = useHistory();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);

  const filtered = useMemo(
    () => filterHistory(events, { query, filter }),
    [events, query, filter],
  );
  const selected = filtered.find((event) => event.event_id === selectedId) ?? null;

  function sendToAssistant(event: HistoryEvent, text: string) {
    const mode: Mode = event.tool_name ? "cloud" : "general";
    navigate("/", { state: { prefill: text, mode } });
  }

  async function copyTranscript(event: HistoryEvent) {
    try {
      await navigator.clipboard.writeText(event.transcript);
    } catch {
      /* clipboard may be unavailable */
    }
  }

  return (
    <div>
      <h1 className="page-title">Transcription History</h1>
      <p className="page-sub">
        Every recognition attempt is recorded here — including failures — for
        debugging. This history is local to this browser and does not sync across
        devices.
      </p>

      <div className="row" style={{ marginBottom: 12 }}>
        <input
          className="input"
          style={{ maxWidth: 320 }}
          placeholder="search transcripts…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="segmented" role="tablist" aria-label="History filter">
          {(["all", "success", "failed"] as Filter[]).map((value) => (
            <button
              key={value}
              type="button"
              className={filter === value ? "active" : ""}
              onClick={() => setFilter(value)}
            >
              {value}
            </button>
          ))}
        </div>
        <div className="spacer" />
        <button
          type="button"
          className="btn btn-sm btn-danger"
          disabled={events.length === 0}
          onClick={() => setConfirmClear(true)}
        >
          clear history
        </button>
      </div>

      {events.length === 0 ? (
        <div className="empty">
          No transcription events yet. Use the microphone or the assistant to
          create one.
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty">No events match the current search or filter.</div>
      ) : (
        <div className="grid grid-2" style={{ alignItems: "start" }}>
          <div>
            {filtered.map((event) => (
              <div
                key={event.event_id}
                className="history-row"
                onClick={() => setSelectedId(event.event_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(keyEvent) => {
                  if (keyEvent.key === "Enter") setSelectedId(event.event_id);
                }}
              >
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <TranscriptionPill status={event.status} />
                  <span className="faint" style={{ fontSize: 11 }}>
                    {formatTime(event.timestamp)}
                  </span>
                </div>
                <div className="transcript">
                  {event.transcript ? event.transcript : <em className="faint">(empty)</em>}
                </div>
                <div className="row faint" style={{ fontSize: 11 }}>
                  <span className="badge">{event.source}</span>
                  <span>{event.provider}</span>
                  {event.tool_name && <span>· {event.tool_name}</span>}
                </div>
              </div>
            ))}
          </div>

          <div>
            {!selected ? (
              <div className="empty">Select an event to inspect it.</div>
            ) : (
              <div className="panel">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <TranscriptionPill status={selected.status} />
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    onClick={() => remove(selected.event_id)}
                  >
                    delete
                  </button>
                </div>

                <p className="panel-title" style={{ marginTop: 12 }}>
                  recognized transcript
                </p>
                {editing === selected.event_id ? (
                  <textarea
                    className="textarea"
                    value={editText}
                    onChange={(event) => setEditText(event.target.value)}
                  />
                ) : (
                  <div className="transcript-text" style={{ fontSize: 16 }}>
                    {selected.transcript || <em className="faint">(empty transcript)</em>}
                  </div>
                )}

                <div className="row" style={{ marginTop: 10 }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => void copyTranscript(selected)}
                  >
                    copy
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => sendToAssistant(selected, selected.transcript)}
                  >
                    retry
                  </button>
                  {editing === selected.event_id ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-sm btn-primary"
                        onClick={() => {
                          sendToAssistant(selected, editText);
                          setEditing(null);
                        }}
                      >
                        resubmit edited
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        onClick={() => setEditing(null)}
                      >
                        cancel
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => {
                        setEditing(selected.event_id);
                        setEditText(selected.transcript);
                      }}
                    >
                      edit transcript
                    </button>
                  )}
                </div>

                <div className="divider" />
                <p className="panel-title">metadata</p>
                <dl className="kv">
                  <dt>event id</dt>
                  <dd>{selected.event_id}</dd>
                  <dt>timestamp</dt>
                  <dd>{selected.timestamp}</dd>
                  <dt>source</dt>
                  <dd>{selected.source}</dd>
                  <dt>provider</dt>
                  <dd>{selected.provider}</dd>
                  <dt>language</dt>
                  <dd>{selected.language ?? "—"}</dd>
                  <dt>confidence</dt>
                  <dd>
                    {selected.confidence != null
                      ? selected.confidence.toFixed(2)
                      : "not provided"}
                  </dd>
                  <dt>duration</dt>
                  <dd>{selected.duration_ms != null ? `${selected.duration_ms} ms` : "—"}</dd>
                  <dt>intent</dt>
                  <dd>{selected.parsed_intent ?? "—"}</dd>
                  <dt>tool</dt>
                  <dd>{selected.tool_name ?? "—"}</dd>
                  <dt>tool status</dt>
                  <dd>{selected.tool_status ?? "—"}</dd>
                </dl>

                <p className="panel-title" style={{ marginTop: 14 }}>
                  status meaning
                </p>
                <div className="faint" style={{ fontSize: 12 }}>
                  {STATUS_META[selected.status]?.description}
                </div>

                {selected.error && (
                  <>
                    <p className="panel-title" style={{ marginTop: 14 }}>
                      error details
                    </p>
                    <div className="alert error">
                      <strong>{selected.error.code}</strong> — {selected.error.message}
                    </div>
                  </>
                )}

                {selected.reply && (
                  <>
                    <p className="panel-title" style={{ marginTop: 14 }}>
                      assistant reply
                    </p>
                    <pre className="mono-block">{selected.reply}</pre>
                  </>
                )}

                <p className="faint" style={{ fontSize: 11, marginTop: 12 }}>
                  History is stored locally in this browser (localStorage). No
                  credentials, authorization headers, or raw audio are stored.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {confirmClear && (
        <ConfirmDialog
          title="Clear all local history?"
          confirmLabel="Clear"
          onCancel={() => setConfirmClear(false)}
          onConfirm={() => {
            clear();
            setSelectedId(null);
            setConfirmClear(false);
          }}
        >
          This removes every event stored in this browser. It cannot be undone.
        </ConfirmDialog>
      )}
    </div>
  );
}
