import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Command } from "../pages/Command";
import { SettingsProvider } from "../state/SettingsContext";

const statusPayload = {
  enabled: false,
  configured: false,
  available: true,
  mode: "simulated",
  provider: "mock-lex",
  detail: "Simulated command provider.",
  setup_hint: "Set LEX_ENABLED=true to use a real bot.",
};

const commandPayload = {
  id: "abc",
  timestamp: "2024-05-01T10:00:00.000Z",
  transcript: "turn on the bedroom fan",
  intent: "DeviceControlIntent",
  slots: { Action: "turn_on", Device: "fan", Room: "bedroom" },
  fulfillment_message: "DEMO — simulated command.",
  mode: "simulated",
  provider: "mock-lex",
  session_id: "synthia-test",
  latency_ms: 3,
  warnings: [],
};

function renderCommand() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <SettingsProvider>
        <Command />
      </SettingsProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = url.includes("/api/lex/status") ? statusPayload : commandPayload;
      return Promise.resolve({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify(body)),
      } as Response);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Command page", () => {
  it("shows the simulated provider status", async () => {
    renderCommand();
    await waitFor(() => {
      expect(screen.getAllByText(/simulated/i).length).toBeGreaterThan(0);
    });
  });

  it("sends a command and renders intent, slots and fulfilment", async () => {
    renderCommand();
    await waitFor(() => expect(screen.getAllByText(/simulated/i).length).toBeGreaterThan(0));

    fireEvent.change(screen.getByLabelText("Command"), {
      target: { value: "turn on the bedroom fan" },
    });
    fireEvent.click(screen.getByRole("button", { name: "send" }));

    await waitFor(() => {
      expect(screen.getByText("DeviceControlIntent")).toBeInTheDocument();
    });
    expect(screen.getByText(/Room/)).toBeInTheDocument();
    expect(screen.getByText("DEMO — simulated command.")).toBeInTheDocument();
    expect(screen.getByText(/DEMO DATA/)).toBeInTheDocument();
  });
});
