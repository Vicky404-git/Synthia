import { useState } from "react";
import type { ToolCall } from "../api/types";
import { apiFetch } from "../api/client";

function ResultTable({
  rows,
  columns,
}: {
  rows: Record<string, unknown>[];
  columns: string[];
}) {
  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column.replace(/_/g, " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{row[column] == null ? "—" : String(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultBody({ result }: { result: Record<string, unknown> }) {
  if (result?.status === "pending_approval") {
    return (
      <div className="alert warn" style={{ marginTop: 8 }}>
        <div style={{ marginBottom: 8 }}>
          <strong>Pending approval</strong> — this tool execution requires human confirmation.
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn primary" onClick={() => { /* Approve handled by parent via API */ }}>
            Approve
          </button>
          <button className="btn">Reject</button>
        </div>
        <pre className="mono-block" style={{ marginTop: 8 }}>
          {JSON.stringify({ tool: result.tool, arguments: result.arguments }, null, 2)}
        </pre>
      </div>
    );
  }
  if (Array.isArray(result.instances)) {
    return (
      <ResultTable
        rows={result.instances as Record<string, unknown>[]}
        columns={["id", "name", "type", "state", "az", "private_ip", "public_ip"]}
      />
    );
  }
  if (Array.isArray(result.buckets)) {
    return (
      <ResultTable
        rows={result.buckets as Record<string, unknown>[]}
        columns={["name", "creation_date"]}
      />
    );
  }
  if (Array.isArray(result.containers)) {
    return (
      <ResultTable
        rows={result.containers as Record<string, unknown>[]}
        columns={["id", "name", "image", "state"]}
      />
    );
  }
  if (Array.isArray(result.lines)) {
    return <pre className="mono-block">{result.lines.join("\n")}</pre>;
  }
  return <pre className="mono-block">{JSON.stringify(result, null, 2)}</pre>;
}

export function ToolCallView({ call }: { call: ToolCall }) {
  const [submitting, setSubmitting] = useState(false);
  const [decision, setDecision] = useState<"pending" | "approved" | "rejected">("pending");

  const isPending =
    decision === "pending" &&
    call.result &&
    typeof call.result === "object" &&
    (call.result as Record<string, unknown>).status === "pending_approval";

  const handleApprove = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await apiFetch("/tools/execute", {
        method: "POST",
        body: JSON.stringify({
          tool: call.name,
          arguments: call.arguments,
          confirmed: true,
        }),
      });
      setDecision("approved");
    } catch (e) {
      // Best effort; UI remains interactive
      setDecision("pending");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = () => {
    setDecision("rejected");
  };

  return (
    <div className="panel" style={{ marginTop: 10 }}>
      <div className="row">
        <strong>{call.name}</strong>
        <span className="badge">{call.provider}</span>
        <span className={`badge ${call.read_only ? "read" : "write"}`}>
          {call.read_only ? "read-only" : "mutating"}
        </span>
        {call.simulated && <span className="pill demo">simulated</span>}
        {isPending && <span className="pill warn">pending approval</span>}
      </div>
      {Object.keys(call.arguments).length > 0 && (
        <pre className="mono-block" style={{ marginTop: 8 }}>
          {JSON.stringify(call.arguments, null, 2)}
        </pre>
      )}
      {isPending && (
        <div className="alert warn" style={{ marginTop: 8 }}>
          <div style={{ marginBottom: 8 }}>
            <strong>Proposed tool execution</strong> — requires explicit approval.
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn primary" onClick={handleApprove} disabled={submitting}>
              {submitting ? "Approving…" : "Approve"}
            </button>
            <button className="btn" onClick={handleReject} disabled={submitting}>
              Reject
            </button>
          </div>
        </div>
      )}
      {!isPending && call.result && <div style={{ marginTop: 8 }}><ResultBody result={call.result as Record<string, unknown>} /></div>}
      {decision === "rejected" && (
        <div className="alert" style={{ marginTop: 8 }}>Execution rejected by user.</div>
      )}
      {call.error && (
        <div className="alert error" style={{ marginTop: 8 }}>
          {JSON.stringify(call.error)}
        </div>
      )}
    </div>
  );
}
