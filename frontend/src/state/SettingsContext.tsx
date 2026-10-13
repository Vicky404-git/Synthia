import { createContext, useContext, type ReactNode } from "react";
import { useLocalStorage } from "../hooks/useLocalStorage";

export type SttKind = "browser" | "server";

export interface SettingsState {
  language: string;
  sttKind: SttKind;
}

interface SettingsContextValue extends SettingsState {
  setLanguage: (language: string) => void;
  setSttKind: (kind: SttKind) => void;
}

export const LANGUAGES: { code: string; label: string }[] = [
  { code: "en-US", label: "English (US)" },
  { code: "en-GB", label: "English (UK)" },
  { code: "en-IN", label: "English (India)" },
  { code: "hi-IN", label: "Hindi (India)" },
  { code: "es-ES", label: "Spanish (Spain)" },
  { code: "fr-FR", label: "French (France)" },
  { code: "de-DE", label: "German (Germany)" },
  { code: "ja-JP", label: "Japanese (Japan)" },
];

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useLocalStorage<SettingsState>("synthia.settings.v1", {
    language: "en-US",
    sttKind: (import.meta.env.VITE_STT_PROVIDER as SttKind) || "browser",
  });

  const value: SettingsContextValue = {
    ...state,
    setLanguage: (language) => setState({ ...state, language }),
    setSttKind: (sttKind) => setState({ ...state, sttKind }),
  };

  return (
    <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
