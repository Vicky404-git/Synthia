import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import {
  addHistoryEvent,
  clearHistory,
  loadHistory,
  removeHistoryEvent,
  updateHistoryEvent,
  type HistoryEvent,
} from "../history/store";

interface HistoryContextValue {
  events: HistoryEvent[];
  add: (event: HistoryEvent) => void;
  update: (eventId: string, patch: Partial<HistoryEvent>) => void;
  remove: (eventId: string) => void;
  clear: () => void;
}

const HistoryContext = createContext<HistoryContextValue | null>(null);

export function HistoryProvider({ children }: { children: ReactNode }) {
  const [events, setEvents] = useState<HistoryEvent[]>(() => loadHistory());

  const add = useCallback((event: HistoryEvent) => {
    setEvents(addHistoryEvent(event));
  }, []);

  const update = useCallback((eventId: string, patch: Partial<HistoryEvent>) => {
    setEvents(updateHistoryEvent(eventId, patch));
  }, []);

  const remove = useCallback((eventId: string) => {
    setEvents(removeHistoryEvent(eventId));
  }, []);

  const clear = useCallback(() => {
    setEvents(clearHistory());
  }, []);

  return (
    <HistoryContext.Provider value={{ events, add, update, remove, clear }}>
      {children}
    </HistoryContext.Provider>
  );
}

export function useHistory(): HistoryContextValue {
  const ctx = useContext(HistoryContext);
  if (!ctx) throw new Error("useHistory must be used within HistoryProvider");
  return ctx;
}
