import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ProviderInfo, ToolExecuteResponse, ToolInfo } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ProviderPill } from "../components/StatusPill";
import { ToolCallView } from "../components/ToolCallView";
import { useBackend } from "../state/BackendContext";

function propertyType(schema: Record<string, unknown>): string {
  if (typeof schema.type === "string") return schema.type;
  const anyOf = schema.anyOf as { type?: string }[] | undefined;
  if (Array.isArray(anyOf)) {
    const found = anyOf.find((entry) => entry.type && entry.type !== "null");
    if (found?.type) return found.type;
  }
  return "string";
}

function ToolCard({ tool }: { tool: ToolInfo }) {
  const properties = (tool.parameters.properties ?? {}) as Record<
    string,
    Record<string, unknown>
  >;
  const required = (tool.parameters.required ?? []) as string[];
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ToolExecuteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function run(confirmed: boolean) {
    setRunning(true);
    setError(null);
    try {
      const args: Record<string, unknown> = {};
      for (const [key, schema] of Object.entries(properties)) {
        const raw = values[key] ?? "";
        const type = propertyType(schema);
        if (type === "boolean") {
          args[key] = raw === "true";
        } else if (type === "integer" || type === "number") {
          if (raw !== "") args[key] = Number(raw);
        } else if (raw !== "") {
          args[key] = raw;
        } else if (required.includes(key)) {
          args[key] = "";
        }
      }
      setResult(await api.executeTool(tool.name, args, confirmed));
    } catch (err) {
      if (err instanceof ApiError && err.code === "confirmation_required") {
        setConfirming(true);
      } else {
        setError(err instanceof ApiError ? `${err.code} — ${err.message}` : String(err));
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="tool-row">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <strong>{tool.name}</strong>
          <span className="badge">{tool.provider}</span>
          <span className={`badge ${tool.read_only ? "read" : "write"}`}>
            {tool.read_only ? "read-only" : "mutating"}
          </span>
        </div>
        <span className={`pill ${tool.available ? "success" : "neutral"}`}>
          {tool.available ? "available" : "unavailable"}
        </span>
      </div>
      <div className="faint" style={{ fontSize: 12, margin: "6px 0" }}>
        {tool.description}
      </div>
      {!tool.available && tool.unavailable_reason && (
        <div className="alert warning" style={{ marginBottom: 8 }}>
          {tool.unavailable_reason}
        </div>
      )}

      {tool.available && (
        <>
          {Object.keys(properties).length > 0 && (
            <div className="grid grid-2" style={{ margin: "8px 0" }}>
              {Object.entries(properties).map(([key, schema]) => {
                const type = propertyType(schema);
                return (
                  <div key={key}>
                    <label className="field-label" htmlFor={`${tool.name}-${key}`}>
                      {key}
                      {required.includes(key) ? " *" : ""}
                    </label>
                    {type === "boolean" ? (
                      <select
                        id={`${tool.name}-${key}`}
                        className="select"
                        value={values[key] ?? "false"}
                        onChange={(event) =>
                          setValues((prev) => ({ ...prev, [key]: event.target.value }))
                        }
                      >
                        <option value="false">false</option>
                        <option value="true">true</option>
                      </select>
                    ) : (
                      <input
                        id={`${tool.name}-${key}`}
                        className="input"
                        placeholder={String(schema.description ?? type)}
                        value={values[key] ?? ""}
                        onChange={(event) =>
                          setValues((prev) => ({ ...prev, [key]: event.target.value }))
                        }
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={running}
            onClick={() => void run(false)}
          >
            {running ? "running…" : "run"}
          </button>
        </>
      )}

      {error && (
        <div className="alert error" style={{ marginTop: 8 }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 10 }}>
          {result.simulated && (
            <div className="alert info" style={{ marginBottom: 6 }}>
              DEMO DATA — this result is simulated and is not a live provider response.
            </div>
          )}
          <ToolCallView
            call={{
              name: result.name,
              provider: result.provider,
              read_only: result.read_only,
              arguments: result.arguments,
              result: result.result,
              error: null,
              requires_confirmation: false,
              simulated: result.simulated,
            }}
          />
        </div>
      )}

      {confirming && (
        <ConfirmDialog
          title="Confirm mutating tool"
          confirmLabel="Execute"
          onCancel={() => setConfirming(false)}
          onConfirm={() => {
            setConfirming(false);
            void run(true);
          }}
        >
          This tool is classified as mutating. In this V1 demonstration it is a
          labelled simulated action only.
        </ConfirmDialog>
      )}
    </div>
  );
}

function ProviderCard({ provider }: { provider: ProviderInfo }) {
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong>{provider.label}</strong>
        <ProviderPill provider={provider} />
      </div>
      <div className="faint" style={{ fontSize: 12, margin: "8px 0" }}>
        {provider.detail}
      </div>
      <div className="row">
        <span className={`badge ${provider.read_only ? "read" : "write"}`}>
          {provider.read_only ? "read-only" : "read/write"}
        </span>
      </div>
      {provider.capabilities.length > 0 && (
        <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12.5 }}>
          {provider.capabilities.map((capability) => (
            <li key={capability}>{capability}</li>
          ))}
        </ul>
      )}
      {provider.setup_hint && (
        <div className="alert info" style={{ marginTop: 8 }}>
          {provider.setup_hint}
        </div>
      )}
    </div>
  );
}

export function Resources() {
  const { providers, loading, error, refresh } = useBackend();
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [toolsError, setToolsError] = useState<string | null>(null);

  useEffect(() => {
    api
      .tools()
      .then((response) => setTools(response.tools))
      .catch((err) =>
        setToolsError(err instanceof ApiError ? err.message : String(err)),
      );
  }, []);

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 className="page-title">Cloud Resources</h1>
          <p className="page-sub">
            Live provider status and the registered read-only operations from
            Synthia's validated tool router.
          </p>
        </div>
        <button type="button" className="btn" onClick={() => void refresh()}>
          {loading ? "refreshing…" : "refresh"}
        </button>
      </div>

      {error && (
        <div className="alert error" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}

      <div className="grid grid-2">
        {providers.map((provider) => (
          <ProviderCard key={provider.id} provider={provider} />
        ))}
      </div>

      <h2 className="page-title" style={{ marginTop: 24, fontSize: 15 }}>
        Registered tools
      </h2>
      <p className="page-sub">
        The LLM may only propose these tools. The backend validates names,
        arguments, permissions, and provider availability before executing.
      </p>

      {toolsError && <div className="alert error">{toolsError}</div>}
      {tools.length === 0 && !toolsError ? (
        <div className="empty">Loading tools…</div>
      ) : (
        tools.map((tool) => <ToolCard key={tool.name} tool={tool} />)
      )}
    </div>
  );
}
