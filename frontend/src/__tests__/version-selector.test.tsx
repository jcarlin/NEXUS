import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { VersionSelector } from "@/components/documents/version-selector";

describe("VersionSelector", () => {
  const members = [
    {
      id: "aaa-111",
      filename: "contract_v1.pdf",
      version_number: 1,
      is_final_version: false,
      created_at: "2025-01-01T00:00:00Z",
    },
    {
      id: "bbb-222",
      filename: "contract_v2.pdf",
      version_number: 2,
      is_final_version: true,
      created_at: "2025-01-02T00:00:00Z",
    },
  ];

  it("renders the label", () => {
    render(
      <VersionSelector
        label="Left"
        members={members}
        value="aaa-111"
        onValueChange={vi.fn()}
      />,
    );
    expect(screen.getByText("Left:")).toBeTruthy();
  });

  it("renders the select trigger", () => {
    const { container } = render(
      <VersionSelector
        label="Right"
        members={members}
        value="bbb-222"
        onValueChange={vi.fn()}
      />,
    );
    // Select trigger should be rendered
    const trigger = container.querySelector("button");
    expect(trigger).toBeTruthy();
  });
});
