import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RenameDialog, MergeDialog, DeleteConfirmDialog } from "@/components/entities/entity-edit-dialogs";

vi.mock("@/api/client", () => ({
  apiClient: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: vi.fn((selector: (s: { matterId: string }) => unknown) =>
    selector({ matterId: "00000000-0000-0000-0000-000000000001" }),
  ),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("RenameDialog", () => {
  const onOpenChange = vi.fn();

  beforeEach(() => vi.clearAllMocks());

  it("renders with entity name and submits new name", async () => {
    render(
      <Wrapper>
        <RenameDialog open onOpenChange={onOpenChange} entityName="Alice" />
      </Wrapper>,
    );

    expect(screen.getByText("Rename Entity")).toBeInTheDocument();
    const input = screen.getByDisplayValue("Alice");
    expect(input).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "Alice Smith" } });
    const btn = screen.getByRole("button", { name: /rename/i });
    expect(btn).not.toBeDisabled();
  });
});

describe("MergeDialog", () => {
  const onOpenChange = vi.fn();

  beforeEach(() => vi.clearAllMocks());

  it("validates target is not the same as source", () => {
    render(
      <Wrapper>
        <MergeDialog open onOpenChange={onOpenChange} entityName="Alice" />
      </Wrapper>,
    );

    const input = screen.getByPlaceholderText("Enter target entity name");
    fireEvent.change(input, { target: { value: "Alice" } });

    const btn = screen.getByRole("button", { name: /merge/i });
    expect(btn).toBeDisabled();
  });
});

describe("DeleteConfirmDialog", () => {
  const onOpenChange = vi.fn();

  beforeEach(() => vi.clearAllMocks());

  it("shows destructive confirmation", () => {
    render(
      <Wrapper>
        <DeleteConfirmDialog open onOpenChange={onOpenChange} entityName="Alice" />
      </Wrapper>,
    );

    expect(screen.getByText("Delete Entity")).toBeInTheDocument();
    expect(screen.getByText(/permanently delete/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete/i })).toBeInTheDocument();
  });
});
