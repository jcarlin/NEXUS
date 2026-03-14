import { createFileRoute } from "@tanstack/react-router";

interface DocumentSearchParams {
  page?: number;
  highlight?: string;
}

export const Route = createFileRoute("/documents/$id")({
  validateSearch: (search: Record<string, unknown>): DocumentSearchParams => ({
    page: typeof search.page === "number" ? search.page : typeof search.page === "string" ? Number(search.page) || undefined : undefined,
    highlight: typeof search.highlight === "string" ? search.highlight : undefined,
  }),
});
