import { BrowserSttProvider } from "./browser";
import { ServerSttProvider } from "./server";
import type { SttProvider } from "./types";

export * from "./types";
export { BrowserSttProvider, mapSpeechError } from "./browser";
export { ServerSttProvider } from "./server";

export type SttProviderKind = "browser" | "server";

export function createSttProvider(kind?: SttProviderKind): SttProvider {
  // Server STT (local Faster-Whisper) is the default: the browser Web Speech API
  // depends on a vendor network service and frequently fails ("network request
  // failed"). A user's explicit preference still wins.
  const configured =
    kind ?? ((import.meta.env.VITE_STT_PROVIDER as SttProviderKind) || "server");
  if (configured === "browser") {
    return new BrowserSttProvider();
  }
  return new ServerSttProvider();
}
