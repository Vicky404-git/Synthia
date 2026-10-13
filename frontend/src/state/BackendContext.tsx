import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError } from "../api/client";
import type { ProviderInfo, ReadyResponse } from "../api/types";

interface BackendContextValue {
  ready: ReadyResponse | null;
  providers: ProviderInfo[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const BackendContext = createContext<BackendContextValue | null>(null);

export function BackendProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [readyResponse, providerResponse] = await Promise.all([
        api.ready(),
        api.providers(),
      ]);
      setReady(readyResponse);
      setProviders(providerResponse.providers);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reach the Synthia backend.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <BackendContext.Provider value={{ ready, providers, loading, error, refresh }}>
      {children}
    </BackendContext.Provider>
  );
}

export function useBackend(): BackendContextValue {
  const ctx = useContext(BackendContext);
  if (!ctx) throw new Error("useBackend must be used within BackendProvider");
  return ctx;
}
