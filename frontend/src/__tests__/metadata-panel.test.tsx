import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetadataPanel } from "@/components/documents/metadata-panel";
import type { DocumentDetail } from "@/types";

const BASE_DOC: DocumentDetail = {
  id: "doc-1",
  filename: "contract.pdf",
  type: "pdf",
  page_count: 25,
  chunk_count: 50,
  entity_count: 12,
  created_at: "2024-03-15T10:00:00Z",
  updated_at: "2024-03-15T10:00:00Z",
  matter_id: "m-1",
  dataset_id: null,
  privilege_status: null,
  hot_doc_score: null,
  anomaly_score: null,
  context_gap_score: null,
  sentiment_positive: null,
  sentiment_negative: null,
  sentiment_pressure: null,
  sentiment_opportunity: null,
  sentiment_rationalization: null,
  sentiment_intent: null,
  sentiment_concealment: null,
  message_id: null,
  in_reply_to: null,
  thread_position: null,
  file_size_bytes: null,
  bates_begin: null,
  bates_end: null,
  privilege_reviewed_at: null,
  context_gaps: [],
} as DocumentDetail;

function makeDoc(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return { ...BASE_DOC, ...overrides } as DocumentDetail;
}

describe("MetadataPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows document info card with filename", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.getByText("Document Info")).toBeInTheDocument();
    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
  });

  it("shows type in uppercase", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.getByText("PDF")).toBeInTheDocument();
  });

  it("shows page count", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.getByText("Pages")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
  });

  it("shows chunk count", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.getByText("Chunks")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });

  it("shows entity count", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.getByText("Entities")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("shows created date formatted", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Mar 15, 2024")).toBeInTheDocument();
  });

  it("shows privilege card when privilege_status is set", () => {
    render(
      <MetadataPanel doc={makeDoc({ privilege_status: "privileged" })} />,
    );
    expect(screen.getByText("Privilege")).toBeInTheDocument();
    expect(screen.getByText("privileged")).toBeInTheDocument();
  });

  it("does not show privilege card when privilege_status is null", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    // "Privilege" as a card title should not be present
    // (there is "Privilege" label in other contexts, but not the card)
    const cards = screen.queryAllByText("Privilege");
    // Only appears in the card header
    expect(cards).toHaveLength(0);
  });

  it("shows privilege review date when available", () => {
    render(
      <MetadataPanel
        doc={makeDoc({
          privilege_status: "privileged",
          privilege_reviewed_at: "2024-03-20T12:00:00Z",
        })}
      />,
    );
    expect(screen.getByText(/Reviewed/)).toBeInTheDocument();
  });

  it("shows email metadata card when message_id is set", () => {
    render(
      <MetadataPanel
        doc={makeDoc({
          message_id: "msg-123@example.com",
          in_reply_to: "msg-100@example.com",
          thread_position: 3,
        })}
      />,
    );
    expect(screen.getByText("Email Metadata")).toBeInTheDocument();
    expect(screen.getByText("Message ID")).toBeInTheDocument();
    expect(screen.getByText("msg-123@example.com")).toBeInTheDocument();
    expect(screen.getByText("In Reply To")).toBeInTheDocument();
    expect(screen.getByText("msg-100@example.com")).toBeInTheDocument();
    expect(screen.getByText("Thread Position")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("does not show email metadata card when message_id is null", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.queryByText("Email Metadata")).not.toBeInTheDocument();
  });

  it("shows sentiment analysis section", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.getByText("Sentiment Analysis")).toBeInTheDocument();
  });

  it("shows sentiment bars when values are present", () => {
    render(
      <MetadataPanel
        doc={makeDoc({
          sentiment_positive: 0.7,
          sentiment_negative: 0.3,
          sentiment_pressure: 0.5,
        })}
      />,
    );
    expect(screen.getByText("Positive")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("Negative")).toBeInTheDocument();
    expect(screen.getByText("30%")).toBeInTheDocument();
    expect(screen.getByText("Pressure")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("shows scoring card when hot_doc_score is set", () => {
    render(
      <MetadataPanel
        doc={makeDoc({
          hot_doc_score: 0.875,
          anomaly_score: 0.456,
          context_gap_score: 0.123,
        })}
      />,
    );
    expect(screen.getByText("Scoring")).toBeInTheDocument();
    expect(screen.getByText("Hot Doc Score")).toBeInTheDocument();
    expect(screen.getByText("0.875")).toBeInTheDocument();
    expect(screen.getByText("Anomaly Score")).toBeInTheDocument();
    expect(screen.getByText("0.456")).toBeInTheDocument();
    expect(screen.getByText("Context Gap")).toBeInTheDocument();
    expect(screen.getByText("0.123")).toBeInTheDocument();
  });

  it("does not show scoring card when hot_doc_score is null", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.queryByText("Scoring")).not.toBeInTheDocument();
  });

  it("shows file size when file_size_bytes is set", () => {
    render(
      <MetadataPanel doc={makeDoc({ file_size_bytes: 512000 })} />,
    );
    expect(screen.getByText("Size")).toBeInTheDocument();
    expect(screen.getByText("500 KB")).toBeInTheDocument();
  });

  it("does not show file size when file_size_bytes is null", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.queryByText("Size")).not.toBeInTheDocument();
  });

  it("shows bates range when both bates_begin and bates_end exist", () => {
    render(
      <MetadataPanel
        doc={makeDoc({ bates_begin: "NEXUS-001", bates_end: "NEXUS-025" })}
      />,
    );
    expect(screen.getByText("Bates")).toBeInTheDocument();
    // The format uses an en-dash separator
    expect(screen.getByText(/NEXUS-001/)).toBeInTheDocument();
    expect(screen.getByText(/NEXUS-025/)).toBeInTheDocument();
  });

  it("does not show bates range when only bates_begin is set", () => {
    render(
      <MetadataPanel doc={makeDoc({ bates_begin: "NEXUS-001" })} />,
    );
    expect(screen.queryByText("Bates")).not.toBeInTheDocument();
  });

  it("does not show bates range when both are null", () => {
    render(<MetadataPanel doc={makeDoc()} />);
    expect(screen.queryByText("Bates")).not.toBeInTheDocument();
  });
});
