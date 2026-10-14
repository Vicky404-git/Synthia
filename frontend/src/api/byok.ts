/**
 * Bring-your-own-key (BYOK) LLM configuration, kept in the browser.
 *
 * Security rules enforced here:
 * - profiles live in `sessionStorage`, never `localStorage`, so they disappear
 *   when the tab closes and are never shared across tabs;
 * - the API key is never written into the bundle, a URL, or a log line;
 * - keys are stored per provider, so switching provider never silently reuses
 *   another provider's key.
 *
 * The key is attached to chat requests only (see `client.ts`) and travels
 * through the Synthia backend to the selected provider — it is not sent to any
 * unrelated endpoint.
 */

export interface LlmProviderDescriptor {
  id: string;
  label: string;
}

/** The providers the backend accepts. Order mirrors the backend registry. */
export const LLM_PROVIDERS: LlmProviderDescriptor[] = [
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Google Gemini" },
  { id: "groq", label: "Groq" },
  { id: "openrouter", label: "OpenRouter" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "together", label: "Together AI" },
  { id: "mistral", label: "Mistral AI" },
  { id: "xai", label: "xAI" },
];

export interface LlmProfile {
  provider: string;
  model: string;
  apiKey: string;
}

export const MAX_MODEL_CHARS = 200;
export const MAX_API_KEY_CHARS = 4096;

const STORAGE_KEY = "synthia.llm.profiles.v1";

interface StoredProfiles {
  active: string | null;
  profiles: Record<string, { model: string; apiKey: string }>;
}

function isKnownProvider(id: string): boolean {
  return LLM_PROVIDERS.some((provider) => provider.id === id);
}

function emptyStore(): StoredProfiles {
  return { active: null, profiles: {} };
}

function readStore(): StoredProfiles {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyStore();
    const parsed = JSON.parse(raw) as Partial<StoredProfiles>;
    const profiles =
      parsed.profiles && typeof parsed.profiles === "object"
        ? Object.fromEntries(
            Object.entries(parsed.profiles).filter(
              ([key, value]) =>
                isKnownProvider(key) &&
                value &&
                typeof value.model === "string" &&
                typeof value.apiKey === "string",
            ),
          )
        : {};
    const active =
      typeof parsed.active === "string" && isKnownProvider(parsed.active)
        ? parsed.active
        : null;
    return { active, profiles };
  } catch {
    return emptyStore();
  }
}

/** Persist the store. Returns false when sessionStorage is unavailable. */
function writeStore(store: StoredProfiles): boolean {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    return true;
  } catch {
    // No silent in-memory fallback: the caller must know persistence failed.
    return false;
  }
}

/** Returns an error message, or null when the profile is valid. */
export function validateProfile(profile: Partial<LlmProfile>): string | null {
  const provider = (profile.provider ?? "").trim();
  if (!provider) return "Choose a provider.";
  if (!isKnownProvider(provider)) return "That provider is not supported.";

  const model = (profile.model ?? "").trim();
  if (!model) return "Enter a model ID.";
  if (model.length > MAX_MODEL_CHARS) {
    return `Model ID must be ${MAX_MODEL_CHARS} characters or fewer.`;
  }

  const apiKey = (profile.apiKey ?? "").trim();
  if (!apiKey) return "Enter an API key for this provider.";
  if (apiKey.length > MAX_API_KEY_CHARS) {
    return `API key must be ${MAX_API_KEY_CHARS} characters or fewer.`;
  }
  return null;
}

/**
 * Persist a profile for its provider and make it the active one.
 *
 * Throws on invalid input, and throws a safe (key-free) error when the browser
 * refuses to persist the profile, so callers never report a false "saved".
 */
export function saveProfile(profile: LlmProfile): void {
  const error = validateProfile(profile);
  if (error) throw new Error(error);
  const store = readStore();
  store.profiles[profile.provider] = {
    model: profile.model.trim(),
    apiKey: profile.apiKey.trim(),
  };
  store.active = profile.provider;
  if (!writeStore(store)) {
    throw new Error(
      "This browser could not save the profile because session storage is " +
        "unavailable. The key was not stored.",
    );
  }
}

/** The stored model/key for a provider, or null when nothing is saved. */
export function getProfileForProvider(
  provider: string,
): { model: string; apiKey: string } | null {
  const store = readStore();
  return store.profiles[provider] ?? null;
}

/** The active profile, or null when chat should use the default provider. */
export function getActiveProfile(): LlmProfile | null {
  const store = readStore();
  if (!store.active) return null;
  const saved = store.profiles[store.active];
  if (!saved) return null;
  return { provider: store.active, model: saved.model, apiKey: saved.apiKey };
}

/**
 * Display-only view of the active profile. Deliberately omits the API key so
 * components can render provider/model status without holding a secret in state.
 */
export interface LlmProfileSummary {
  provider: string;
  model: string;
}

/** The active provider and model, or null when the default provider is used. */
export function getActiveProfileSummary(): LlmProfileSummary | null {
  const profile = getActiveProfile();
  return profile ? { provider: profile.provider, model: profile.model } : null;
}

/** Remove every saved profile, returning chat to the default/demo provider. */
export function clearProfiles(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/**
 * Headers to attach to chat requests only. Empty when no profile is active.
 * Never call this for non-chat endpoints.
 */
export function byokHeaders(): Record<string, string> {
  const profile = getActiveProfile();
  if (!profile) return {};
  return {
    "X-Synthia-LLM-Provider": profile.provider,
    "X-Synthia-LLM-Model": profile.model,
    "X-Synthia-LLM-API-Key": profile.apiKey,
  };
}
