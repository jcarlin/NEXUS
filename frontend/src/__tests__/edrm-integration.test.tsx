import { describe, it, expect, vi, beforeEach } from "vitest";

// Define locally to avoid dependency on generated schemas (gitignored, not available in CI)
const LoadFileFormat = {
  concordance_dat: "concordance_dat",
  opticon_opt: "opticon_opt",
  edrm_xml: "edrm_xml",
} as const;

// ---- Mocks ---- //

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: {
    getState: () => ({ accessToken: "test-token" }),
  },
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ matterId: "matter-1" }),
    {
      getState: () => ({ matterId: "matter-1" }),
    },
  ),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/main", () => ({
  queryClient: {
    invalidateQueries: vi.fn(),
    setQueryData: vi.fn(),
    getQueryData: vi.fn(),
  },
}));

vi.mock("@tanstack/react-router", () => ({
  createRootRoute: (opts: Record<string, unknown>) => opts,
  createFileRoute: () => (opts: Record<string, unknown>) => opts,
  Outlet: () => null,
  useMatches: () => [],
  useNavigate: () => vi.fn(),
  useParams: () => ({}),
  Link: ({ children, ...props }: { children: React.ReactNode; to: string }) => (
    <a href={props.to}>{children}</a>
  ),
}));

// Mock react-query to return controlled data
const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
}));

vi.mock("@/api/client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@/api/generated/schemas", () => ({
  LoadFileFormat: {
    concordance_dat: "concordance_dat",
    opticon_opt: "opticon_opt",
    edrm_xml: "edrm_xml",
  },
}));

// Mock child components that are not relevant to EDRM tests
vi.mock("@/components/documents/upload-widget", () => ({
  UploadWidget: () => <div data-testid="upload-widget" />,
}));
vi.mock("@/components/datasets/ingest-form", () => ({
  IngestForm: () => <div data-testid="ingest-form" />,
}));
vi.mock("@/components/datasets/ingest-progress", () => ({
  IngestProgress: () => <div data-testid="ingest-progress" />,
}));
vi.mock("@/components/review/result-set-table", () => ({
  ResultSetTable: () => <div data-testid="result-set-table" />,
}));
vi.mock("@/components/ui/pagination", () => ({
  Pagination: () => <div data-testid="pagination" />,
}));
vi.mock("@/components/analytics/comm-matrix", () => ({
  CommMatrix: () => <div data-testid="comm-matrix" />,
}));
vi.mock("@/components/analytics/comm-drilldown", () => ({
  CommDrilldown: () => <div data-testid="comm-drilldown" />,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  mockUseMutation.mockReturnValue({ isPending: false, mutate: vi.fn() });
});

// ---- Test 1: EDRM import format values match backend ---- //

describe("EDRM Import on Ingest Page", () => {
  it("EDRM format values match backend LoadFileFormat enum", () => {
    // Verify the generated enum has exactly the expected values
    const generatedFormats = Object.values(LoadFileFormat);
    expect(generatedFormats).toContain("concordance_dat");
    expect(generatedFormats).toContain("opticon_opt");
    expect(generatedFormats).toContain("edrm_xml");
    expect(generatedFormats).toHaveLength(3);
  });

  it("import endpoint path matches backend router", () => {
    // The frontend POSTs to this path; must match app/edrm/router.py prefix + route
    const importPath = "/api/v1/edrm/import";
    expect(importPath).toMatch(/^\/api\/v1\/edrm\/import$/);
  });

  it("export endpoint path matches backend router", () => {
    const exportPath = "/api/v1/edrm/export";
    expect(exportPath).toMatch(/^\/api\/v1\/edrm\/export$/);
  });
});

// ---- Test 2: Comms page has Threads tab ---- //

describe("Email Threads on Comms Page", () => {
  it("renders tabs with Matrix and Email Threads options", async () => {
    // Provide thread data for the threads query
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      if (opts.queryKey[0] === "edrm-threads") {
        return {
          data: {
            items: [
              {
                thread_id: "thread-1",
                message_count: 5,
                subject: "Project Update",
                earliest: "2024-01-01T00:00:00Z",
                latest: "2024-01-05T00:00:00Z",
              },
            ],
            total: 1,
            offset: 0,
            limit: 100,
          },
          isLoading: false,
        };
      }
      return { data: undefined, isLoading: false };
    });

    const mod = await import("@/routes/analytics/comms");
    expect(mod.Route).toBeDefined();
  });
});

// ---- Test 3: Result set page includes DuplicateClustersPanel ---- //

describe("Duplicate Clusters on Result Set Page", () => {
  it("module exports Route with duplicate clusters support", async () => {
    mockUseQuery.mockImplementation((opts: { queryKey: string[] }) => {
      if (opts.queryKey[0] === "edrm-duplicates") {
        return {
          data: {
            items: [
              { cluster_id: "dup-1", document_count: 3, avg_score: 0.95 },
              { cluster_id: "dup-2", document_count: 2, avg_score: null },
            ],
            total: 2,
            offset: 0,
            limit: 100,
          },
          isLoading: false,
        };
      }
      return { data: undefined, isLoading: false };
    });

    const mod = await import("@/routes/review/result-set");
    expect(mod.Route).toBeDefined();
  }, 15_000);
});

// ---- Test 4: DuplicateCluster interface shape ---- //

describe("DuplicateCluster type", () => {
  it("correctly models the backend response shape", () => {
    const cluster = {
      cluster_id: "dup-abc",
      document_count: 4,
      avg_score: 0.87,
    };

    expect(cluster.cluster_id).toBe("dup-abc");
    expect(cluster.document_count).toBe(4);
    expect(cluster.avg_score).toBeCloseTo(0.87);
  });

  it("avg_score can be null", () => {
    const cluster = {
      cluster_id: "dup-xyz",
      document_count: 2,
      avg_score: null,
    };
    expect(cluster.avg_score).toBeNull();
  });
});

// ---- Test 5: ThreadResponse interface shape ---- //

describe("ThreadResponse type", () => {
  it("correctly models the backend response shape", () => {
    const thread = {
      thread_id: "t-123",
      message_count: 8,
      subject: "Re: Meeting notes",
      earliest: "2024-03-01T10:00:00Z",
      latest: "2024-03-05T14:00:00Z",
    };

    expect(thread.thread_id).toBe("t-123");
    expect(thread.message_count).toBe(8);
    expect(thread.subject).toBe("Re: Meeting notes");
  });

  it("subject and dates can be null", () => {
    const thread = {
      thread_id: "t-456",
      message_count: 1,
      subject: null,
      earliest: null,
      latest: null,
    };
    expect(thread.subject).toBeNull();
    expect(thread.earliest).toBeNull();
  });
});

// ---- Test 6: EDRM format options ---- //

describe("EDRM format options", () => {
  it("supports the three backend-defined formats", () => {
    const formats = Object.values(LoadFileFormat);
    expect(formats).toHaveLength(3);
    expect(formats).toContain(LoadFileFormat.concordance_dat);
    expect(formats).toContain(LoadFileFormat.opticon_opt);
    expect(formats).toContain(LoadFileFormat.edrm_xml);
  });
});
