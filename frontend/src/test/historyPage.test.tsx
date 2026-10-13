import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { History } from "../pages/History";
import { HistoryProvider } from "../state/HistoryContext";
import type { HistoryEvent } from "../history/store";

const KEY = "synthia.history.v1";

const seeded: HistoryEvent[] = [
  {
    event_id: "evt-success",
    timestamp: "2024-05-01T10:00:00.000Z",
    transcript: "show all containers",
    provider: "browser-webspeech",
    source: "speech",
    status: "success",
    confidence: 0.9,
    local_only: true,
  },
  {
    event_id: "evt-denied",
    timestamp: "2024-05-01T10:01:00.000Z",
    transcript: "",
    provider: "browser-webspeech",
    source: "speech",
    status: "permission_denied",
    error: { code: "not-allowed", message: "Microphone permission was denied." },
    local_only: true,
  },
];

function renderHistory() {
  return render(
    <MemoryRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <HistoryProvider>
        <History />
      </HistoryProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(KEY, JSON.stringify(seeded));
});

describe("History page", () => {
  it("shows both successful and failed attempts with distinct statuses", () => {
    renderHistory();
    expect(screen.getByText("show all containers")).toBeInTheDocument();
    expect(screen.getByText("Transcribed")).toBeInTheDocument();
    expect(screen.getByText("Permission denied")).toBeInTheDocument();
  });

  it("shows an empty state when there is no history", () => {
    localStorage.setItem(KEY, JSON.stringify([]));
    renderHistory();
    expect(screen.getByText(/No transcription events yet/i)).toBeInTheDocument();
  });
});
