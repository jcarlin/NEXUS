import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import React from "react";
import { PageSkeleton } from "@/components/ui/page-skeleton";

describe("PageSkeleton", () => {
  it("renders default 5 skeleton rows", () => {
    const { container } = render(<PageSkeleton />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    // 2 header skeletons + 5 row skeletons = 7
    expect(skeletons.length).toBe(7);
  });

  it("renders custom number of rows", () => {
    const { container } = render(<PageSkeleton rows={3} />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    // 2 header skeletons + 3 row skeletons = 5
    expect(skeletons.length).toBe(5);
  });

  it("renders header skeletons", () => {
    const { container } = render(<PageSkeleton />);
    // First child has the header skeletons
    const firstSection = container.querySelector('.space-y-2');
    expect(firstSection).toBeTruthy();
    const headerSkeletons = firstSection!.querySelectorAll('[class*="animate-pulse"]');
    expect(headerSkeletons.length).toBe(2);
  });
});
