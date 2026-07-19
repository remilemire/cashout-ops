import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cashoutApi } from "@/api/cashout";
import { ApiError } from "@/api/client";
import type { CashoutDocumentAnalysis, CashoutSubmission } from "@/api/types";

import { NewCashoutPage } from "./NewCashoutPage";

vi.mock("@/api/cashout", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/cashout")>();
  return {
    ...actual,
    cashoutApi: {
      ...actual.cashoutApi,
      createSubmission: vi.fn(),
      uploadDocument: vi.fn(),
    },
  };
});

const createSubmissionMock = vi.mocked(cashoutApi.createSubmission);
const uploadDocumentMock = vi.mocked(cashoutApi.uploadDocument);

const submission: CashoutSubmission = {
  id: "submission-1",
  createdAt: "2026-07-17T00:00:00Z",
  status: "PROCESSING",
  submittedByUserId: "user-1",
  submittedAt: "2026-07-17T00:00:00Z",
};

const analysis: CashoutDocumentAnalysis = {
  id: "analysis-1",
  createdAt: "2026-07-17T00:00:00Z",
  provider: "ANTHROPIC",
  model: "test-model",
  status: "EXTRACTING",
  classification: null,
  classificationConfidence: null,
  schemaName: null,
  extractedDataJson: null,
  extractionConfidence: null,
  issues: null,
  errorCode: null,
  errorMessage: null,
  completedAt: null,
  verifiedDataJson: null,
  verifiedByUserId: null,
  verifiedAt: null,
  cashoutDocumentId: "document-1",
};

const pdf = new File(["%PDF-1.4"], "receipt.pdf", {
  type: "application/pdf",
});

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "/cashouts/new", element: <NewCashoutPage /> },
      {
        path: "/cashouts/:submissionId",
        element: <div>Cashout detail</div>,
      },
    ],
    { initialEntries: ["/cashouts/new"] },
  );

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  return router;
}

beforeEach(() => {
  createSubmissionMock.mockReset();
  uploadDocumentMock.mockReset();
  createSubmissionMock.mockResolvedValue(submission);
  uploadDocumentMock.mockResolvedValue(analysis);
});

describe("NewCashoutPage", () => {
  it("waits for the first document before creating the submission", async () => {
    const router = renderPage();

    expect(createSubmissionMock).not.toHaveBeenCalled();
    expect(screen.getByText(/^Cashout —/)).toBeDefined();
    expect(screen.getByText("In progress")).toBeDefined();

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });

    await waitFor(() =>
      expect(uploadDocumentMock).toHaveBeenCalledWith("submission-1", pdf),
    );
    expect(await screen.findByText("Cashout detail")).toBeDefined();
    expect(createSubmissionMock).toHaveBeenCalledTimes(1);
    expect(router.state.location.pathname).toBe("/cashouts/submission-1");
  });

  it("reuses the created submission when the first upload is retried", async () => {
    uploadDocumentMock.mockRejectedValueOnce(
      new ApiError(500, {
        kind: "INTERNAL",
        code: "INTERNAL",
        message: "Upload failed.",
      }),
    );
    renderPage();

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });
    expect(await screen.findByText("Upload failed.")).toBeDefined();

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });
    expect(await screen.findByText("Cashout detail")).toBeDefined();

    expect(createSubmissionMock).toHaveBeenCalledTimes(1);
    expect(uploadDocumentMock).toHaveBeenCalledTimes(2);
    expect(uploadDocumentMock).toHaveBeenNthCalledWith(2, "submission-1", pdf);
  });
});
