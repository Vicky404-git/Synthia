import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveProfile } from "../api/byok";
import { Settings } from "../pages/Settings";
import { BackendProvider } from "../state/BackendContext";
import { HistoryProvider } from "../state/HistoryContext";
import { SettingsProvider } from "../state/SettingsContext";

// Keep the real byok module but intercept saveProfile so we can simulate a
// persistence failure without touching the (working) sessionStorage in jsdom.
vi.mock("../api/byok", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/byok")>();
  return { ...actual, saveProfile: vi.fn(actual.saveProfile) };
});

const readyPayload = {
  service: "synthia",
  version: "0.1.0",
  environment: "test",
  demo_mode: true,
  dependencies: [],
};

const providersPayload = { providers: [] };

function renderSettings() {
  return render(
    <SettingsProvider>
      <BackendProvider>
        <HistoryProvider>
          <Settings />
        </HistoryProvider>
      </BackendProvider>
    </SettingsProvider>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  vi.mocked(saveProfile).mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        text: () =>
          Promise.resolve(
            JSON.stringify(
              url.includes("/api/providers") ? providersPayload : readyPayload,
            ),
          ),
      } as Response),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Settings BYOK", () => {
  it("keeps the key and reports no active profile when storage fails", async () => {
    vi.mocked(saveProfile).mockImplementationOnce(() => {
      throw new Error(
        "This browser could not save the profile because session storage is " +
          "unavailable. The key was not stored.",
      );
    });

    renderSettings();
    await waitFor(() =>
      expect(screen.getByText(/backend url/i)).toBeInTheDocument(),
    );

    const model = screen.getByLabelText("model id") as HTMLInputElement;
    const key = screen.getByLabelText("api key") as HTMLInputElement;
    fireEvent.change(model, { target: { value: "gpt-4o-mini" } });
    fireEvent.change(key, { target: { value: "sk-secret-value" } });

    fireEvent.click(screen.getByRole("button", { name: /save & use/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/session storage is unavailable/i),
      ).toBeInTheDocument(),
    );
    // The typed key is preserved so the user can retry.
    expect(key.value).toBe("sk-secret-value");
    // No active profile is claimed.
    expect(screen.getByText(/using default provider/i)).toBeInTheDocument();
  });

  it("clears the key and shows the active provider on success", async () => {
    renderSettings();
    await waitFor(() =>
      expect(screen.getByText(/backend url/i)).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByLabelText("model id"), {
      target: { value: "gpt-4o-mini" },
    });
    fireEvent.change(screen.getByLabelText("api key"), {
      target: { value: "sk-secret-value" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save & use/i }));

    await waitFor(() =>
      expect(screen.getByText(/active: openai/i)).toBeInTheDocument(),
    );
    expect((screen.getByLabelText("api key") as HTMLInputElement).value).toBe("");
  });
});
