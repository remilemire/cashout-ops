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
  classification: "manual_note",
  classificationConfidence: 0.95,
  schemaName: "manual_note",
  extractedDataJson: { note: "cash $100" },
  extractionConfidence: 0.9,
  issues: null,
  errorCode: null,
  errorMessage: null,
  completedAt: "2026-07-17T01:01:00Z",
  verifiedDataJson: { note: "cash $100" },
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
});
