// frontend/src/features/cashout/NewCashoutPage.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
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
      uploadManualDocument: vi.fn(),
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

const createSubmissionMock = vi.mocked(cashoutApi.createSubmission);
const uploadDocumentMock = vi.mocked(cashoutApi.uploadDocument);
const uploadManualDocumentMock = vi.mocked(cashoutApi.uploadManualDocument);

const submission: CashoutSubmission = {
  id: "submission-1",
  createdAt: "2026-07-17T00:00:00Z",
  status: "processing",
  employeeUserId: "user-1",
  submittedAt: "2026-07-17T00:00:00Z",
  businessDate: "2026-07-17",
  completedByUserId: null,
  firstCompletedAt: null,
  tipoutDepartments: null,
  updatedAt: "2026-07-17T00:00:00Z",
};

/**
 * Expected dates via the same LOCAL-date logic the page uses — not
 * toISOString(), which renders the UTC day and diverges in the evening in
 * negative-offset timezones.
 */
function localDay(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

const analysis: CashoutDocumentAnalysis = {
  id: "analysis-1",
  createdAt: "2026-07-17T00:00:00Z",
  provider: "anthropic",
  model: "test-model",
  status: "extracting",
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
  uploadManualDocumentMock.mockReset();
  createSubmissionMock.mockResolvedValue(submission);
  uploadDocumentMock.mockResolvedValue(analysis);
  uploadManualDocumentMock.mockResolvedValue({
    ...analysis,
    status: "verified",
    provider: null,
    model: null,
  });
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

  it("creates the submission for today's local date by default", async () => {
    renderPage();

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });

    await waitFor(() => expect(createSubmissionMock).toHaveBeenCalledOnce());
    expect(createSubmissionMock).toHaveBeenCalledWith({
      businessDate: localDay(),
    });
  });

  it("creates the submission for yesterday when the cashier picks it", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Yesterday" }));
    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });

    await waitFor(() => expect(createSubmissionMock).toHaveBeenCalledOnce());
    expect(createSubmissionMock).toHaveBeenCalledWith({
      businessDate: localDay(-1),
    });
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

  it("creates the submission through the manual-entry flow", async () => {
    const router = renderPage();

    expect(createSubmissionMock).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Or enter details manually" }),
    );
    const dialog = screen.getByRole("dialog", {
      name: "Enter document details",
    });

    fireEvent.change(dialog.querySelector('input[type="file"]')!, {
      target: { files: [pdf] },
    });
    fireEvent.change(within(dialog).getByLabelText("Total net sales"), {
      target: { value: "1500.00" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Add details" }),
    );

    await waitFor(() =>
      expect(uploadManualDocumentMock).toHaveBeenCalledOnce(),
    );
    expect(createSubmissionMock).toHaveBeenCalledTimes(1);
    expect(uploadManualDocumentMock).toHaveBeenCalledWith("submission-1", pdf, {
      classification: "touchbistro_report",
      data: {
        food_net_sales: "",
        drink_net_sales: "",
        total_net_sales: "1500.00",
        cash_payment_total: "",
        card_payment_total: "",
        card_transaction_count: "",
        card_tip_total: "",
      },
    });
    expect(await screen.findByText("Cashout detail")).toBeDefined();
    expect(router.state.location.pathname).toBe("/cashouts/submission-1");
  });
});
