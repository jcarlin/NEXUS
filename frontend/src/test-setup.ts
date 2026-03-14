import "@testing-library/jest-dom/vitest";
import { QueryClient } from "@tanstack/react-query";

// Mock @/main to prevent createRoot() side effect at module load
// (app-store.ts imports queryClient from main.tsx, which calls createRoot)
vi.mock("@/main", () => ({
  queryClient: new QueryClient({
    defaultOptions: { queries: { retry: false } },
  }),
}));

// Mock react-pdf to avoid pdfjs-dist loading (uses Promise.withResolvers, needs Node 22+)
vi.mock("react-pdf", () => ({
  Document: ({ children }: any) => children,
  Page: () => null,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));
