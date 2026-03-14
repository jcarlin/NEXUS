import { createFileRoute } from "@tanstack/react-router";

interface ThreadSearchParams {
  followUp?: string;
}

export const Route = createFileRoute("/chat/$threadId")({
  validateSearch: (search: Record<string, unknown>): ThreadSearchParams => ({
    followUp: typeof search.followUp === "string" ? search.followUp : undefined,
  }),
});
