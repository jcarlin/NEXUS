import { create } from "zustand";
import { persist } from "zustand/middleware";

interface DevModeStore {
  enabled: boolean;
  toggle: () => void;
}

export const useDevModeStore = create<DevModeStore>()(
  persist(
    (set) => ({
      enabled: false,
      toggle: () => set((s) => ({ enabled: !s.enabled })),
    }),
    { name: "nexus-dev-mode" },
  ),
);
