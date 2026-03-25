import { createContext, useContext, useState, useCallback, useMemo } from "react";
import type { ReactNode } from "react";

interface LiveRefreshContextValue {
  isLive: boolean;
  toggleLive: () => void;
}

const LiveRefreshContext = createContext<LiveRefreshContextValue | null>(null);

export function LiveRefreshProvider({ children }: { children: ReactNode }) {
  const [isLive, setIsLive] = useState(true);
  const toggleLive = useCallback(() => setIsLive((prev) => !prev), []);
  const value = useMemo(() => ({ isLive, toggleLive }), [isLive, toggleLive]);
  return (
    <LiveRefreshContext.Provider value={value}>
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
