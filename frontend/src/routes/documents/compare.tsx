import { createFileRoute } from "@tanstack/react-router";

interface CompareSearchParams {
  left: string;
  right: string;
}

export const Route = createFileRoute("/documents/compare")({
  validateSearch: (
    search: Record<string, unknown>,
  ): CompareSearchParams => ({
    left: typeof search.left === "string" ? search.left : "",
    right: typeof search.right === "string" ? search.right : "",
  }),
});
