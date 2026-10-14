import { API_BASE, hasApiToken, setApiToken } from "../api/client";
import {
  LLM_PROVIDERS,
  clearProfiles,
  getActiveProfileSummary,
  getProfileForProvider,
  saveProfile,
  validateProfile,
  type LlmProfile,
  type LlmProfileSummary,
} from "../api/byok";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ProviderPill } from "../components/StatusPill";
import { getSpeechRecognitionCtor } from "../stt/browser";
import { LANGUAGES, useSettings, type SttKind } from "../state/SettingsContext";
import { useBackend } from "../state/BackendContext";
import { useHistory } from "../state/HistoryContext";
import { useState } from "react";

export function Settings() {
  const {
    language,
    setLanguage,
    sttKind,
    setSttKind,
    wakeWordEnabled,
    setWakeWordEnabled,
  } = useSettings();
  const { ready, providers, error } = useBackend();
  const { events, clear } = useHistory();
  const [confirmClear, setConfirmClear] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [tokenSet, setTokenSet] = useState(() => hasApiToken());

  // BYOK: the selected provider's saved profile, if any. The key itself is
  // never read back into the UI — only whether one is saved for this provider.
  const [byokProvider, setByokProvider] = useState(LLM_PROVIDERS[0].id);
  const [byokModel, setByokModel] = useState(
    () => getProfileForProvider(LLM_PROVIDERS[0].id)?.model ?? "",
  );
  const [byokKey, setByokKey] = useState("");
  const [byokError, setByokError] = useState<string | null>(null);
  const [byokSaved, setByokSaved] = useState(
    () => getProfileForProvider(LLM_PROVIDERS[0].id) !== null,
  );
  // Display metadata only — the API key is never held in component state.
  const [activeProfile, setActiveProfile] = useState<LlmProfileSummary | null>(
    () => getActiveProfileSummary(),
  );

  // Evaluated once per mount: whether this browser can even do keyword spotting.
  const speechSupported = getSpeechRecognitionCtor() !== undefined;

  function selectByokProvider(id: string) {
    setByokProvider(id);
    setByokKey("");
    setByokError(null);
    const saved = getProfileForProvider(id);
    setByokModel(saved?.model ?? "");
    setByokSaved(Boolean(saved));
  }

  function handleSaveByok() {
    // Reuse this provider's already-saved key when the field is left blank.
    const existing = getProfileForProvider(byokProvider);
    const apiKey = byokKey.trim() || existing?.apiKey || "";
    const profile: LlmProfile = { provider: byokProvider, model: byokModel, apiKey };
    const error = validateProfile(profile);
    if (error) {
      setByokError(error);
      return;
    }
    try {
      saveProfile(profile);
    } catch (err) {
      // Persistence failed: keep the typed key so the user can retry, and never
      // report the profile as saved/active.
      setByokError(
        err instanceof Error ? err.message : "Could not save this profile.",
      );
      return;
    }
    setByokKey("");
    setByokError(null);
    setByokSaved(true);
    setActiveProfile(getActiveProfileSummary());
  }

  function handleClearByok() {
    clearProfiles();
    setByokKey("");
    setByokModel("");
    setByokSaved(false);
    setByokError(null);
    setActiveProfile(null);
  }

  const llm = ready?.dependencies.find((dep) => dep.name === "llm");
  const stt = ready?.dependencies.find((dep) => dep.name === "stt");
  const lex = ready?.dependencies.find((dep) => dep.name === "lex");

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
          <dt>command recognition</dt>
          <dd>{lex?.detail ?? "—"}</dd>
        </dl>
      </div>

      <div className="panel">
        <p className="panel-title">voice commands</p>
        <p className="faint" style={{ fontSize: 12.5 }}>
          The <strong>Commands</strong> page uses a replaceable intent
          recogniser. With no AWS Lex configuration it runs a clearly labelled
          simulated provider, so the flow works offline. Configure{" "}
          <code>LEX_ENABLED</code>, <code>LEX_BOT_ID</code>, and{" "}
          <code>LEX_BOT_ALIAS_ID</code> on the backend to use a real AWS Lex V2
          bot; results are then marked <strong>live AWS</strong>. Synthia sends
          only text or a transcript — never raw audio stored on the server.
        </p>
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
        <p className="panel-title">ai provider — bring your own key</p>
        <p className="faint" style={{ fontSize: 12.5 }}>
          Use your own AI provider for chat. Choose a provider, enter a model ID
          and your API key. The key is kept only in this browser tab's session
          storage (never in localStorage or the build) and is sent with chat
          requests to the Synthia backend, which forwards the request to the
          provider you selected.
        </p>
        <div className="alert warning" style={{ marginTop: 10 }}>
          <strong>Privacy &amp; billing.</strong> Your prompts and chat history
          pass through the Synthia backend to the selected provider, where that
          provider's data, retention, and billing policies apply. Usage is billed
          by the provider against your own key and may incur charges. Synthia does
          not verify the key here — the provider may reject it on your next chat
          request.
        </div>

        <div className="grid grid-2" style={{ marginTop: 10 }}>
          <div>
            <label className="field-label" htmlFor="byok-provider">
              provider
            </label>
            <select
              id="byok-provider"
              className="select"
              value={byokProvider}
              onChange={(event) => selectByokProvider(event.target.value)}
            >
              {LLM_PROVIDERS.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="byok-model">
              model id
            </label>
            <input
              id="byok-model"
              className="input"
              type="text"
              placeholder="e.g. gpt-4o-mini"
              value={byokModel}
              onChange={(event) => setByokModel(event.target.value)}
            />
          </div>
        </div>

        <div style={{ marginTop: 10 }}>
          <label className="field-label" htmlFor="byok-key">
            api key
          </label>
          <input
            id="byok-key"
            className="input"
            style={{ maxWidth: 420 }}
            type="password"
            autoComplete="off"
            placeholder={byokSaved ? "key saved for this session" : "paste API key…"}
            value={byokKey}
            onChange={(event) => setByokKey(event.target.value)}
          />
        </div>

        {byokError && (
          <div className="alert error" style={{ marginTop: 10 }}>
            {byokError}
          </div>
        )}

        <div className="row" style={{ marginTop: 10 }}>
          <button type="button" className="btn" onClick={handleSaveByok}>
            save &amp; use
          </button>
          <button type="button" className="btn btn-ghost" onClick={handleClearByok}>
            clear
          </button>
          <span className={`pill ${activeProfile ? "success" : "neutral"}`}>
            {activeProfile
              ? `active: ${activeProfile.provider} · ${activeProfile.model}`
              : "using default provider"}
          </span>
        </div>
        <p className="faint" style={{ fontSize: 11.5, marginTop: 10 }}>
          Switching provider keeps each provider's own saved key; it never reuses
          another provider's key. The saved key is never displayed again. Clearing
          returns chat to the server's default/demo provider and does not affect
          your API access token.
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
              <option value="server">Server STT via backend (recommended)</option>
              <option value="browser">Browser Web Speech API</option>
            </select>
          </div>
        </div>
        <div className="alert warning" style={{ marginTop: 10 }}>
          <strong>Server STT</strong> records audio in the browser and uploads it
          to the Synthia backend, which transcribes it. With the default{" "}
          <strong>local Faster-Whisper</strong> provider, the audio is processed
          on the backend host only and is never sent to a third party. The
          browser Web Speech API instead relies on the browser vendor and
          frequently fails. Typed input is always available as a fallback.
        </div>
      </div>

      <div className="panel">
        <p className="panel-title">wake word (“synthia”)</p>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div style={{ maxWidth: 560 }}>
            <div>
              Say <strong>“Synthia”</strong> to arm the microphone while you are on
              the Assistant page. The wake phrase only <em>starts</em> listening —
              it never sends a request on its own; the transcript is still shown
              for review before you send it.
            </div>
            <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>
              Off by default. Manual push-to-talk always stays available, even if
              wake-word mode is unsupported or fails. If the browser speech service
              drops the connection, the listener re-arms automatically with a
              bounded backoff (and waits for the network while offline); only a
              denied microphone or a missing device stops it.
            </div>
          </div>
          <button
            type="button"
            className={`btn ${wakeWordEnabled ? "btn-primary" : ""}`}
            aria-pressed={wakeWordEnabled}
            onClick={() => setWakeWordEnabled(!wakeWordEnabled)}
          >
            {wakeWordEnabled ? "on" : "off"}
          </button>
        </div>

        {!speechSupported && (
          <div className="alert warning" style={{ marginTop: 10 }}>
            This browser does not expose the Web Speech API, so wake-word
            detection is unavailable here. The microphone button and typed input
            still work.
          </div>
        )}

        <div className="alert warning" style={{ marginTop: 10 }}>
          <strong>Privacy — this is not an offline feature.</strong> Wake-word
          detection uses the browser Web Speech API purely for keyword spotting.
          Many browsers (Chrome included) send microphone audio to the browser
          vendor to recognise speech, so audio may leave your device while wake
          mode is armed. Your actual request is then transcribed by the configured
          server recogniser — with the default <strong>local Faster-Whisper</strong>{" "}
          provider that audio stays on the backend host, but it is never sent to
          your browser vendor for transcription. Turn wake mode off to stop all
          listening immediately.
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
