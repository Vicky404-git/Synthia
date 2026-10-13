import { BrowserSttProvider } from "./browser";
import { ServerSttProvider } from "./server";
import type { SttProvider } from "./types";

export * from "./types";
export { BrowserSttProvider, mapSpeechError } from "./browser";
export { ServerSttProvider } from "./server";

export type SttProviderKind = "browser" | "server";

export function createSttProvider(kind?: SttProviderKind): SttProvider {
  const configured =
    kind ?? ((import.meta.env.VITE_STT_PROVIDER as SttProviderKind) || "browser");
  if (configured === "server") {
    return new ServerSttProvider();
  }
  return new BrowserSttProvider();
}
