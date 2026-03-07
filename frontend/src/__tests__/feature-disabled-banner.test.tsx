import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FeatureDisabledBanner } from "@/components/ui/feature-disabled-banner";

describe("FeatureDisabledBanner", () => {
  it("renders with the feature name", () => {
    render(<FeatureDisabledBanner featureName="Hot Document Detection" />);

    expect(screen.getByText("Hot Document Detection")).toBeInTheDocument();
    expect(
      screen.getByText(/Contact your administrator/),
    ).toBeInTheDocument();
  });

  it("renders as an alert", () => {
    render(<FeatureDisabledBanner featureName="Topic Clustering" />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Topic Clustering")).toBeInTheDocument();
  });

  it("shows the feature name in bold", () => {
    render(<FeatureDisabledBanner featureName="Reranker" />);

    const strong = screen.getByText("Reranker");
    expect(strong.tagName).toBe("STRONG");
  });
});
