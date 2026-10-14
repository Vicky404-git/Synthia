import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  LLM_PROVIDERS,
  MAX_API_KEY_CHARS,
  MAX_MODEL_CHARS,
  byokHeaders,
  clearProfiles,
  getActiveProfile,
  getActiveProfileSummary,
  getProfileForProvider,
  saveProfile,
  validateProfile,
} from "../api/byok";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

describe("LLM provider list", () => {
  it("exposes the eight supported providers", () => {
    expect(LLM_PROVIDERS.map((provider) => provider.id)).toEqual([
      "openai",
      "gemini",
      "groq",
      "openrouter",
      "deepseek",
      "together",
      "mistral",
      "xai",
    ]);
  });
});

describe("validateProfile", () => {
  it("requires a known provider, a model and a key", () => {
    expect(validateProfile({ provider: "", model: "m", apiKey: "k" })).toMatch(
      /provider/i,
    );
    expect(
      validateProfile({ provider: "unknown", model: "m", apiKey: "k" }),
    ).toMatch(/not supported/i);
    expect(validateProfile({ provider: "groq", model: "", apiKey: "k" })).toMatch(
      /model/i,
    );
    expect(validateProfile({ provider: "groq", model: "m", apiKey: "  " })).toMatch(
      /api key/i,
    );
    expect(
      validateProfile({ provider: "groq", model: "m", apiKey: "k" }),
    ).toBeNull();
  });

  it("rejects oversized model ids and keys", () => {
    expect(
      validateProfile({
        provider: "groq",
        model: "x".repeat(MAX_MODEL_CHARS + 1),
        apiKey: "k",
      }),
    ).toMatch(/model/i);
    expect(
      validateProfile({
        provider: "groq",
        model: "m",
        apiKey: "k".repeat(MAX_API_KEY_CHARS + 1),
      }),
    ).toMatch(/api key/i);
  });
});

describe("profile storage", () => {
  it("saves and reads back the active profile from sessionStorage", () => {
    saveProfile({ provider: "groq", model: "llama-3.1-8b", apiKey: "sk-test" });
    expect(getActiveProfile()).toEqual({
      provider: "groq",
      model: "llama-3.1-8b",
      apiKey: "sk-test",
    });
    expect(sessionStorage.getItem("synthia.llm.profiles.v1")).toBeTruthy();
  });

  it("never writes the key to localStorage", () => {
    saveProfile({ provider: "openai", model: "gpt-4o-mini", apiKey: "sk-secret" });
    expect(localStorage.length).toBe(0);
  });

  it("keeps per-provider keys and never reuses them across providers", () => {
    saveProfile({ provider: "groq", model: "m-groq", apiKey: "key-groq" });
    saveProfile({ provider: "xai", model: "m-xai", apiKey: "key-xai" });

    expect(getProfileForProvider("groq")).toEqual({
      model: "m-groq",
      apiKey: "key-groq",
    });
    expect(getProfileForProvider("xai")).toEqual({
      model: "m-xai",
      apiKey: "key-xai",
    });
    // The most recently saved provider is the active one.
    expect(getActiveProfile()?.provider).toBe("xai");
  });

  it("ignores unknown providers when reading a tampered store", () => {
    sessionStorage.setItem(
      "synthia.llm.profiles.v1",
      JSON.stringify({
        active: "evil",
        profiles: { evil: { model: "m", apiKey: "k" } },
      }),
    );
    expect(getActiveProfile()).toBeNull();
    expect(getProfileForProvider("evil")).toBeNull();
  });

  it("clears everything back to the default provider", () => {
    saveProfile({ provider: "mistral", model: "m", apiKey: "k" });
    clearProfiles();
    expect(getActiveProfile()).toBeNull();
    expect(sessionStorage.getItem("synthia.llm.profiles.v1")).toBeNull();
  });

  it("throws a safe error and stores nothing when sessionStorage rejects writes", () => {
    const setItem = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("QuotaExceededError");
      });
    expect(() =>
      saveProfile({ provider: "groq", model: "llama", apiKey: "sk-secret" }),
    ).toThrow(/session storage/i);
    setItem.mockRestore();

    // Nothing was persisted: no active profile and no headers.
    expect(getActiveProfile()).toBeNull();
    expect(byokHeaders()).toEqual({});
  });

  it("exposes only provider and model in the active summary", () => {
    saveProfile({ provider: "xai", model: "grok-2", apiKey: "sk-secret" });
    expect(getActiveProfileSummary()).toEqual({
      provider: "xai",
      model: "grok-2",
    });
  });
});

describe("byokHeaders", () => {
  it("is empty when no profile is active", () => {
    clearProfiles();
    expect(byokHeaders()).toEqual({});
  });

  it("returns all three headers for the active profile", () => {
    saveProfile({ provider: "deepseek", model: "deepseek-chat", apiKey: "k" });
    expect(byokHeaders()).toEqual({
      "X-Synthia-LLM-Provider": "deepseek",
      "X-Synthia-LLM-Model": "deepseek-chat",
      "X-Synthia-LLM-API-Key": "k",
    });
  });
});
