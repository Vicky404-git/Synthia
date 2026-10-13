import { beforeEach, describe, expect, it } from "vitest";
import {
  addHistoryEvent,
  clearHistory,
  filterHistory,
  loadHistory,
  type HistoryEvent,
} from "../history/store";

function event(partial: Partial<HistoryEvent>): HistoryEvent {
  return {
    event_id: partial.event_id ?? Math.random().toString(36).slice(2),
    timestamp: partial.timestamp ?? new Date().toISOString(),
    transcript: partial.transcript ?? "show all containers",
    provider: partial.provider ?? "browser-webspeech",
    source: partial.source ?? "speech",
    status: partial.status ?? "success",
    local_only: true,
    ...partial,
  };
}

beforeEach(() => {
  localStorage.clear();
});

describe("history store", () => {
  it("persists and reloads events", () => {
    addHistoryEvent(event({ transcript: "list ec2" }));
    const loaded = loadHistory();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].transcript).toBe("list ec2");
  });

  it("keeps failed attempts distinct from successes", () => {
    addHistoryEvent(event({ status: "success" }));
    addHistoryEvent(event({ status: "permission_denied", transcript: "" }));
    addHistoryEvent(event({ status: "network_failure", transcript: "" }));

    const all = loadHistory();
    expect(filterHistory(all, { query: "", filter: "all" })).toHaveLength(3);
    expect(filterHistory(all, { query: "", filter: "success" })).toHaveLength(1);
    expect(filterHistory(all, { query: "", filter: "failed" })).toHaveLength(2);
  });

  it("searches by transcript text", () => {
    addHistoryEvent(event({ transcript: "show all containers" }));
    addHistoryEvent(event({ transcript: "list s3 buckets" }));
    const results = filterHistory(loadHistory(), { query: "s3", filter: "all" });
    expect(results).toHaveLength(1);
    expect(results[0].transcript).toContain("s3");
  });

  it("clears history", () => {
    addHistoryEvent(event({}));
    clearHistory();
    expect(loadHistory()).toHaveLength(0);
  });
});
