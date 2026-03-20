import { createContext, useContext, useState, useCallback } from "react";
import type { ReactNode } from "react";

interface LiveRefreshContextValue {
  isLive: boolean;
  toggleLive: () => void;
}

const LiveRefreshContext = createContext<LiveRefreshContextValue | null>(null);

export function LiveRefreshProvider({ children }: { children: ReactNode }) {
  const [isLive, setIsLive] = useState(true);
  const toggleLive = useCallback(() => setIsLive((prev) => !prev), []);
  return (
    <LiveRefreshContext.Provider value={{ isLive, toggleLive }}>
      {children}
    </LiveRefreshContext.Provider>
  );
}

export function useLiveRefresh(): LiveRefreshContextValue {
  const ctx = useContext(LiveRefreshContext);
  // Graceful degradation: when no provider exists (e.g. CeleryPanel on /admin/operations)
  if (!ctx) return { isLive: true, toggleLive: () => {} };
  return ctx;
}
