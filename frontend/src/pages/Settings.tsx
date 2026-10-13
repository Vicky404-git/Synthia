import { API_BASE, hasApiToken, setApiToken } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ProviderPill } from "../components/StatusPill";
import { LANGUAGES, useSettings, type SttKind } from "../state/SettingsContext";
import { useBackend } from "../state/BackendContext";
import { useHistory } from "../state/HistoryContext";
import { useState } from "react";

export function Settings() {
  const { language, setLanguage, sttKind, setSttKind } = useSettings();
  const { ready, providers, error } = useBackend();
  const { events, clear } = useHistory();
  const [confirmClear, setConfirmClear] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [tokenSet, setTokenSet] = useState(() => hasApiToken());

  const llm = ready?.dependencies.find((dep) => dep.name === "llm");
  const stt = ready?.dependencies.find((dep) => dep.name === "stt");

  return (
    <div>
      <h1 className="page-title">Settings</h1>
      <p className="page-sub">
        Configuration status and privacy controls. Secret values are never
        displayed in the browser.
      </p>

      {error && (
        <div className="alert error" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}

      <div className="panel">
        <p className="panel-title">runtime</p>
        <dl className="kv">
          <dt>backend url</dt>
          <dd>{API_BASE || "same origin (dev proxy / relative)"}</dd>
          <dt>service</dt>
          <dd>
            {ready ? `${ready.service} v${ready.version}` : "unreachable"}
          </dd>
          <dt>environment</dt>
          <dd>{ready?.environment ?? "—"}</dd>
          <dt>mode</dt>
          <dd>
            {ready?.demo_mode ? (
              <span className="pill demo">demo mode</span>
            ) : (
              <span className="pill success">configured</span>
            )}
          </dd>
          <dt>llm</dt>
          <dd>{llm?.detail ?? "—"}</dd>
          <dt>speech-to-text</dt>
          <dd>{stt?.detail ?? "—"}</dd>
        </dl>
      </div>

      <div className="panel">
        <p className="panel-title">provider configuration status</p>
        <div className="row">
          {providers.map((provider) => (
            <ProviderPill key={provider.id} provider={provider} />
          ))}
        </div>
        <p className="faint" style={{ fontSize: 11.5, marginTop: 10 }}>
          Only providers marked <strong>connected</strong> are live. Everything
          else is either demo data, unconfigured, or planned. No credentials,
          tokens, or headers are ever sent to or shown in the browser.
        </p>
      </div>

      <div className="panel">
        <p className="panel-title">speech recognition</p>
        <div className="grid grid-2">
          <div>
            <label className="field-label" htmlFor="language">
              recognition language
            </label>
            <select
              id="language"
              className="select"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
            >
              {LANGUAGES.map((entry) => (
                <option key={entry.code} value={entry.code}>
                  {entry.label} ({entry.code})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="stt-kind">
              recogniser
            </label>
            <select
              id="stt-kind"
              className="select"
              value={sttKind}
              onChange={(event) => setSttKind(event.target.value as SttKind)}
            >
              <option value="browser">Browser Web Speech API</option>
              <option value="server">Hosted STT via backend</option>
            </select>
          </div>
        </div>
        <div className="alert warning" style={{ marginTop: 10 }}>
          Browser speech recognition availability varies. Some browsers send
          audio to a vendor service even when using the Web Speech API. The
          hosted option sends audio to the Synthia backend. Typed input is always
          available as a fallback.
        </div>
      </div>

      <div className="panel">
        <p className="panel-title">api access token (this session only)</p>
        <p className="faint" style={{ fontSize: 12.5 }}>
          Optional. Required only when the backend sets API_AUTH_TOKEN. The value
          is kept in sessionStorage for this browser session and is never baked
          into the build or displayed again here.
        </p>
        <div className="row" style={{ marginTop: 8 }}>
          <input
            className="input"
            style={{ maxWidth: 320 }}
            type="password"
            placeholder={tokenSet ? "token is set" : "paste token…"}
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
          />
          <button
            type="button"
            className="btn"
            onClick={() => {
              setApiToken(tokenInput);
              setTokenSet(hasApiToken());
              setTokenInput("");
            }}
          >
            save
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              setApiToken("");
              setTokenSet(false);
              setTokenInput("");
            }}
          >
            clear
          </button>
          <span className={`pill ${tokenSet ? "success" : "neutral"}`}>
            {tokenSet ? "token set" : "no token"}
          </span>
        </div>
      </div>

      <div className="panel">
        <p className="panel-title">privacy & local history</p>
        <p className="faint" style={{ fontSize: 12.5 }}>
          Transcription history ({events.length} events) is stored only in this
          browser's localStorage. It does not sync across devices or users. No
          raw audio, credentials, authorization headers, or cloud responses with
          secrets are stored.
        </p>
        <button
          type="button"
          className="btn btn-danger"
          style={{ marginTop: 10 }}
          disabled={events.length === 0}
          onClick={() => setConfirmClear(true)}
        >
          clear local history
        </button>
      </div>

      {confirmClear && (
        <ConfirmDialog
          title="Clear all local history?"
          confirmLabel="Clear"
          onCancel={() => setConfirmClear(false)}
          onConfirm={() => {
            clear();
            setConfirmClear(false);
          }}
        >
          This removes every event stored in this browser. It cannot be undone.
        </ConfirmDialog>
      )}
    </div>
  );
}
