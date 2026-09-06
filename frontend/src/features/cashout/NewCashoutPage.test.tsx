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
      updateSubmission: vi.fn(),
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
const updateSubmissionMock = vi.mocked(cashoutApi.updateSubmission);
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
 * Today via the same LOCAL-date logic the page uses — not toISOString(),
 * which renders the UTC day and diverges in the evening in negative-offset
 * timezones.
 */
function localToday(): string {
  const date = new Date();
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
  schemaVersion: null,
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
  updateSubmissionMock.mockReset();
  uploadDocumentMock.mockReset();
  uploadManualDocumentMock.mockReset();
  // Echo the requested day: a retry compares the created submission's day
  // against the picker, and the fixture's fixed day would otherwise differ
  // from today and trigger a spurious re-date.
  createSubmissionMock.mockImplementation(async (input) => ({
    ...submission,
    businessDate: input?.businessDate ?? localToday(),
  }));
  updateSubmissionMock.mockImplementation(async (_id, input) => ({
    ...submission,
    businessDate: input.businessDate,
  }));
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
      businessDate: localToday(),
    });
  });

  it("creates the submission for the picked date", async () => {
    // Any date, not just yesterday: a cashier can catch up a day from last
    // week.
    renderPage();

    fireEvent.change(screen.getByLabelText("Cashout for"), {
      target: { value: "2026-08-20" },
    });
    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });

    await waitFor(() => expect(createSubmissionMock).toHaveBeenCalledOnce());
    expect(createSubmissionMock).toHaveBeenCalledWith({
      businessDate: "2026-08-20",
    });
  });

  it("reuses the created submission when the first upload is retried", async () => {
    uploadDocumentMock.mockRejectedValueOnce(
      new ApiError(500, {
        kind: "INTERNAL",
        code: "INTERNAL",
        ctx: {},
      }),
    );
    renderPage();

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });
    expect(await screen.findByText("Something went wrong.")).toBeDefined();

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });
    expect(await screen.findByText("Cashout detail")).toBeDefined();

    expect(createSubmissionMock).toHaveBeenCalledTimes(1);
    expect(updateSubmissionMock).not.toHaveBeenCalled();
    expect(uploadDocumentMock).toHaveBeenCalledTimes(2);
    expect(uploadDocumentMock).toHaveBeenNthCalledWith(2, "submission-1", pdf);
  });

  it("keeps the date editable after a failed first upload", async () => {
    // The submission exists now, but its day stays open until completion.
    uploadDocumentMock.mockRejectedValueOnce(
      new ApiError(500, {
        kind: "INTERNAL",
        code: "INTERNAL",
        ctx: {},
      }),
    );
    renderPage();

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });
    expect(await screen.findByText("Something went wrong.")).toBeDefined();

    expect(
      screen.getByLabelText<HTMLInputElement>("Cashout for"),
    ).toHaveProperty("disabled", false);
  });

  it("re-dates the created submission when the day changes before the retry", async () => {
    uploadDocumentMock.mockRejectedValueOnce(
      new ApiError(500, {
        kind: "INTERNAL",
        code: "INTERNAL",
        ctx: {},
      }),
    );
    renderPage();

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });
    expect(await screen.findByText("Something went wrong.")).toBeDefined();

    fireEvent.change(screen.getByLabelText("Cashout for"), {
      target: { value: "2026-08-20" },
    });
    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });
    expect(await screen.findByText("Cashout detail")).toBeDefined();

    expect(createSubmissionMock).toHaveBeenCalledTimes(1);
    expect(updateSubmissionMock).toHaveBeenCalledWith("submission-1", {
      businessDate: "2026-08-20",
    });
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
