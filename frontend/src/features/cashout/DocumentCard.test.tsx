// frontend/src/features/cashout/DocumentCard.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cashoutApi } from "@/api/cashout";
import type { CashoutDocument, CashoutDocumentAnalysis } from "@/api/types";

import { DocumentCard } from "./DocumentCard";

vi.mock("@/api/cashout", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/cashout")>();
  return {
    ...actual,
    cashoutApi: {
      ...actual.cashoutApi,
      getAnalysis: vi.fn(),
      deleteDocument: vi.fn(),
      unverifyAnalysis: vi.fn(),
      extractDocument: vi.fn(),
    },
  };
});

vi.mock("@/components/dialog", () => ({
  Dialog: ({
    open,
    title,
    children,
  }: {
    open: boolean;
    title: string;
    children: ReactNode;
  }) =>
    open ? (
      <div role="dialog" aria-label={title}>
        <h2>{title}</h2>
        {children}
      </div>
    ) : null,
}));

const getAnalysisMock = vi.mocked(cashoutApi.getAnalysis);
const deleteDocumentMock = vi.mocked(cashoutApi.deleteDocument);
const unverifyAnalysisMock = vi.mocked(cashoutApi.unverifyAnalysis);
const extractDocumentMock = vi.mocked(cashoutApi.extractDocument);

const analysis: CashoutDocumentAnalysis = {
  id: "analysis-1",
  createdAt: "2026-07-17T01:00:00Z",
  provider: "anthropic",
  model: "claude-sonnet-5",
  status: "verified",
  classification: "server_summary_report",
  classificationConfidence: 0.95,
  schemaName: "ServerSummaryReportData",
  extractedDataJson: {
    grand_total: "1234.56",
    grand_total_transaction_count: 42,
  },
  extractionConfidence: 0.9,
  issues: null,
  errorCode: null,
  errorMessage: null,
  completedAt: "2026-07-17T01:01:00Z",
  verifiedDataJson: {
    grand_total: "1234.56",
    grand_total_transaction_count: 42,
  },
  verifiedByUserId: "user-1",
  verifiedAt: "2026-07-17T01:02:00Z",
  cashoutDocumentId: "document-1",
};

const needsVerificationAnalysis: CashoutDocumentAnalysis = {
  ...analysis,
  status: "needs_verification",
  verifiedDataJson: null,
  verifiedByUserId: null,
  verifiedAt: null,
};

const cashoutDocument: CashoutDocument = {
  id: "document-1",
  createdAt: "2026-07-17T01:00:00Z",
  contentType: "application/pdf",
  originalFilename: "receipt.pdf",
  checksumSha256: "abc123",
  uploadedByUserId: "user-1",
  uploadedAt: "2026-07-17T01:00:00Z",
  cashoutSubmissionId: "submission-1",
  analysis,
};

function renderCard(
  editable: boolean,
  document: CashoutDocument = cashoutDocument,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <DocumentCard
        document={document}
        submissionId="submission-1"
        editable={editable}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getAnalysisMock.mockReset();
  deleteDocumentMock.mockReset();
  unverifyAnalysisMock.mockReset();
  extractDocumentMock.mockReset();
  getAnalysisMock.mockResolvedValue(analysis);
  deleteDocumentMock.mockResolvedValue(undefined);
  unverifyAnalysisMock.mockResolvedValue(needsVerificationAnalysis);
  extractDocumentMock.mockResolvedValue({
    ...needsVerificationAnalysis,
    status: "extracting",
  });
});

describe("DocumentCard", () => {
  it("hides the remove option when not editable", () => {
    renderCard(false);

    expect(screen.getByText("receipt.pdf")).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Remove document" }),
    ).toBeNull();
  });

  it("confirms and removes the document", async () => {
    renderCard(true);

    fireEvent.click(screen.getByRole("button", { name: "Remove document" }));
    const dialog = screen.getByRole("dialog", { name: "Remove document?" });

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Remove document" }),
    );

    await waitFor(() => expect(deleteDocumentMock).toHaveBeenCalledOnce());
    expect(deleteDocumentMock.mock.calls[0]?.[0]).toBe("document-1");
  });

  it("edits a verified analysis by unverifying it", async () => {
    renderCard(true);

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    await waitFor(() => expect(unverifyAnalysisMock).toHaveBeenCalledOnce());
    expect(unverifyAnalysisMock.mock.calls[0]?.[0]).toBe("analysis-1");
  });

  it("hides the edit option when not editable", () => {
    renderCard(false);

    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  });

  it("labels the verified summary from the schema registry", () => {
    renderCard(false);

    expect(screen.getByText("Grand total")).toBeDefined();
    expect(screen.getByText("Orders")).toBeDefined();
    expect(screen.queryByText("Grand total transaction count")).toBeNull();
  });

  it("keeps curated labels on the original extraction inside the correction note", () => {
    const corrected: CashoutDocumentAnalysis = {
      ...analysis,
      verifiedDataJson: {
        grand_total: "1200.00",
        grand_total_transaction_count: 42,
      },
    };
    getAnalysisMock.mockResolvedValue(corrected);
    renderCard(false, { ...cashoutDocument, analysis: corrected });

    expect(
      screen.getByText(/corrected from the original extraction/i),
    ).toBeDefined();
    // Once in the verified summary, once in the correction note's extraction.
    expect(screen.getAllByText("Grand total")).toHaveLength(2);
    expect(screen.getAllByText("Orders")).toHaveLength(2);
  });

  it("offers retry extraction while needs-verification", async () => {
    getAnalysisMock.mockResolvedValue(needsVerificationAnalysis);
    renderCard(true, {
      ...cashoutDocument,
      analysis: needsVerificationAnalysis,
    });

    fireEvent.click(screen.getByRole("button", { name: "Retry extraction" }));

    await waitFor(() => expect(extractDocumentMock).toHaveBeenCalledOnce());
    expect(extractDocumentMock.mock.calls[0]?.[0]).toBe("document-1");
  });

  it("corrects the classification and re-runs the extraction", async () => {
    getAnalysisMock.mockResolvedValue(needsVerificationAnalysis);
    renderCard(true, {
      ...cashoutDocument,
      analysis: needsVerificationAnalysis,
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Correct document type" }),
    );
    const dialog = screen.getByRole("dialog", {
      name: "Correct document type",
    });
    // Brand casing comes from the curated labels, not enumLabel.
    expect(
      within(dialog).getByRole("option", { name: "TouchBistro report" }),
    ).toBeDefined();
    // "Unknown" has nothing to extract, so it is not offered as a correction.
    expect(
      within(dialog).queryByRole("option", { name: "Unknown" }),
    ).toBeNull();

    fireEvent.change(within(dialog).getByLabelText("Document type"), {
      target: { value: "touchbistro_report" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Re-run extraction" }),
    );

    await waitFor(() => expect(extractDocumentMock).toHaveBeenCalledOnce());
    expect(extractDocumentMock.mock.calls[0]).toEqual([
      "document-1",
      { classification: "touchbistro_report" },
    ]);
    // The mutation lands the extracting analysis in the cache: the card is
    // back in the extracting state (and polls from there as usual).
    expect(await screen.findByText("Reading the document…")).toBeDefined();
  });

  it("keeps the unchanged classification from re-running", () => {
    getAnalysisMock.mockResolvedValue(needsVerificationAnalysis);
    renderCard(true, {
      ...cashoutDocument,
      analysis: needsVerificationAnalysis,
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Correct document type" }),
    );
    const dialog = screen.getByRole("dialog", {
      name: "Correct document type",
    });

    // The select defaults to the current classification; confirming an
    // identical rerun is disabled rather than firing a pointless extraction.
    const confirm = within(dialog).getByRole("button", {
      name: "Re-run extraction",
    });
    expect(confirm).toHaveProperty("disabled", true);
  });

  it("hides the classification correction when not editable", () => {
    getAnalysisMock.mockResolvedValue(needsVerificationAnalysis);
    renderCard(false, {
      ...cashoutDocument,
      analysis: needsVerificationAnalysis,
    });

    expect(
      screen.queryByRole("button", { name: "Correct document type" }),
    ).toBeNull();
  });
});
