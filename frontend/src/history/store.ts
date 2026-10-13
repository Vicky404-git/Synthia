import type {
  InputSource,
  TranscriptionStatus,
} from "../api/types";

export interface HistoryEvent {
  event_id: string;
  timestamp: string;
  transcript: string;
  provider: string;
  language?: string;
  source: InputSource;
  status: TranscriptionStatus;
  confidence?: number;
  parsed_intent?: string | null;
  tool_name?: string | null;
  tool_status?: TranscriptionStatus | null;
  error?: { code: string; message: string } | null;
  duration_ms?: number;
  reply?: string;
  /** V1 history is browser-local and never synchronised. */
  local_only: true;
}

const STORAGE_KEY = "synthia.history.v1";
const MAX_EVENTS = 200;

export function newEventId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `evt_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export function loadHistory(): HistoryEvent[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as HistoryEvent[];
  } catch {
    return [];
  }
}

export function saveHistory(events: HistoryEvent[]): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(events.slice(0, MAX_EVENTS)));
  } catch {
    /* storage may be unavailable (private mode); history is best-effort */
  }
}

export function addHistoryEvent(event: HistoryEvent): HistoryEvent[] {
  const events = [event, ...loadHistory()].slice(0, MAX_EVENTS);
  saveHistory(events);
  return events;
}

export function updateHistoryEvent(
  eventId: string,
  patch: Partial<HistoryEvent>,
): HistoryEvent[] {
  const events = loadHistory().map((event) =>
    event.event_id === eventId ? { ...event, ...patch } : event,
  );
  saveHistory(events);
  return events;
}

export function removeHistoryEvent(eventId: string): HistoryEvent[] {
  const events = loadHistory().filter((event) => event.event_id !== eventId);
  saveHistory(events);
  return events;
}

export function clearHistory(): HistoryEvent[] {
  saveHistory([]);
  return [];
}

export function filterHistory(
  events: HistoryEvent[],
  opts: { query: string; filter: "all" | "success" | "failed" },
): HistoryEvent[] {
  const query = opts.query.trim().toLowerCase();
  return events.filter((event) => {
    if (opts.filter === "success" && event.status !== "success" && event.status !== "tool_succeeded") {
      return false;
    }
    if (opts.filter === "failed") {
      const failed =
        event.status !== "success" &&
        event.status !== "tool_succeeded" &&
        (event.status !== "empty_transcript" || event.transcript.trim() === "");
      if (!failed) return false;
    }
    if (!query) return true;
    return (
      event.transcript.toLowerCase().includes(query) ||
      (event.tool_name ?? "").toLowerCase().includes(query) ||
      event.status.toLowerCase().includes(query)
    );
  });
}
