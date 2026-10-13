import type { ToolCall } from "../api/types";

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
  return (
    <div className="panel" style={{ marginTop: 10 }}>
      <div className="row">
        <strong>{call.name}</strong>
        <span className="badge">{call.provider}</span>
        <span className={`badge ${call.read_only ? "read" : "write"}`}>
          {call.read_only ? "read-only" : "mutating"}
        </span>
        {call.simulated && <span className="pill demo">simulated</span>}
      </div>
      {Object.keys(call.arguments).length > 0 && (
        <pre className="mono-block" style={{ marginTop: 8 }}>
          {JSON.stringify(call.arguments, null, 2)}
        </pre>
      )}
      {call.result && <div style={{ marginTop: 8 }}><ResultBody result={call.result} /></div>}
      {call.error && (
        <div className="alert error" style={{ marginTop: 8 }}>
          {JSON.stringify(call.error)}
        </div>
      )}
    </div>
  );
}
