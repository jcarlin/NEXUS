import { create } from "zustand";
import { persist } from "zustand/middleware";

interface OnboardingState {
  completed: boolean;
  currentStep: number;
  run: boolean;

  startTour: () => void;
  completeTour: () => void;
  resetTour: () => void;
  setCurrentStep: (step: number) => void;
}

export const useOnboarding = create<OnboardingState>()(
  persist(
    (set) => ({
      completed: false,
      currentStep: 0,
      run: false,

      startTour: () => set({ run: true, currentStep: 0 }),
      completeTour: () => set({ completed: true, run: false, currentStep: 0 }),
      resetTour: () => set({ completed: false, currentStep: 0, run: false }),
      setCurrentStep: (step) => set({ currentStep: step }),
    }),
    {
      name: "nexus-onboarding-v1",
      partialize: (state) => ({
        completed: state.completed,
      }),
    },
  ),
);
