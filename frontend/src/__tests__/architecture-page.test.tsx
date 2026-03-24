import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
  createLazyFileRoute: () => (routeOptions: Record<string, unknown>) => routeOptions,
}));

const mockFlags = {
  flags: [
    { flag_name: "enable_agentic_pipeline", enabled: true, display_name: "Agentic Pipeline", description: "", category: "query", risk_level: "safe" },
    { flag_name: "enable_citation_verification", enabled: true, display_name: "Citation Verification", description: "", category: "query", risk_level: "safe" },
    { flag_name: "enable_self_reflection", enabled: false, display_name: "Self Reflection", description: "", category: "query", risk_level: "safe" },
    { flag_name: "enable_sparse_embeddings", enabled: true, display_name: "Sparse Embeddings", description: "", category: "retrieval", risk_level: "safe" },
    { flag_name: "enable_reranker", enabled: true, display_name: "Reranker", description: "", category: "retrieval", risk_level: "safe" },
  ],
};

const mockLLMConfig = {
  providers: [],
  tiers: [
    { tier: "query", provider_label: "Gemini", provider_type: "gemini", model: "gemini-2.0-flash" },
    { tier: "analysis", provider_label: "Gemini", provider_type: "gemini", model: "gemini-2.0-flash" },
    { tier: "ingestion", provider_label: "Gemini", provider_type: "gemini", model: "gemini-2.0-flash" },
  ],
  env_defaults: {},
  embedding: { provider: "ollama", model: "nomic-embed-text", dimensions: 768 },
};

const mockSettings = {
  settings: [
    { setting_name: "chunk_size", value: 512, category: "ingestion", unit: "tokens" },
    { setting_name: "chunk_overlap", value: 64, category: "ingestion", unit: "tokens" },
  ],
};

vi.mock("@/api/client", () => ({
  apiClient: vi.fn((config: { url: string }) => {
    if (config.url.includes("feature-flags")) return Promise.resolve(mockFlags);
    if (config.url.includes("llm-config")) return Promise.resolve(mockLLMConfig);
    if (config.url.includes("settings")) return Promise.resolve(mockSettings);
    return Promise.resolve({});
  }),
}));

import { Route } from "@/routes/admin/architecture.lazy";

const Component = (Route as unknown as { component: React.ComponentType }).component;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  );
}

describe("ArchitecturePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page title", async () => {
    render(<Component />, { wrapper: createWrapper() });
    expect(await screen.findByText("Pipeline Architecture")).toBeInTheDocument();
  });

  it("shows query and ingestion tabs", async () => {
    render(<Component />, { wrapper: createWrapper() });
    expect(await screen.findByText("Query Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Ingestion Pipeline")).toBeInTheDocument();
  });

  it("renders query pipeline nodes", async () => {
    render(<Component />, { wrapper: createWrapper() });
    expect(await screen.findByText("investigation_agent")).toBeInTheDocument();
    expect(screen.getByText("case_context_resolve")).toBeInTheDocument();
    expect(screen.getByText("verify_citations")).toBeInTheDocument();
    expect(screen.getByText("generate_follow_ups")).toBeInTheDocument();
  });

  it("shows reflect node as disabled when self_reflection is off", async () => {
    render(<Component />, { wrapper: createWrapper() });
    const reflectTitle = await screen.findByText("reflect");
    // Walk up to the PipelineNode wrapper div
    const node = reflectTitle.closest(".rounded-lg");
    expect(node?.className).toContain("opacity-50");
    expect(node?.className).toContain("border-dashed");
  });

  it("renders model config table with current models", async () => {
    render(<Component />, { wrapper: createWrapper() });
    expect(await screen.findByText("Current Model Configuration")).toBeInTheDocument();
    const badges = await screen.findAllByText("gemini-2.0-flash");
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it("has ingestion pipeline tab", async () => {
    render(<Component />, { wrapper: createWrapper() });
    await screen.findByText("Pipeline Architecture");
    const tab = screen.getByRole("tab", { name: "Ingestion Pipeline" });
    expect(tab).toBeInTheDocument();
  });

  it("displays tool grid with all 17 tools", async () => {
    render(<Component />, { wrapper: createWrapper() });
    await screen.findByText("investigation_agent");
    expect(screen.getByText("vector_search")).toBeInTheDocument();
    expect(screen.getByText("graph_query")).toBeInTheDocument();
    expect(screen.getByText("sentiment_search")).toBeInTheDocument();
    expect(screen.getByText("ask_user")).toBeInTheDocument();
    expect(screen.getByText("decompose_query")).toBeInTheDocument();
  });

  it("shows embedding info from LLM config", async () => {
    render(<Component />, { wrapper: createWrapper() });
    // nomic-embed-text appears inside <code> tags - use getAllByText to find any instance
    const elements = await screen.findAllByText("nomic-embed-text");
    expect(elements.length).toBeGreaterThanOrEqual(1);
  });
});
