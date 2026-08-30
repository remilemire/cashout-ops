// frontend/src/features/cashout/SubmissionPage.test.tsx

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
import type { CashoutSubmissionDetail, User } from "@/api/types";
import { useAuth } from "@/auth/useAuth";

import { SubmissionPage } from "./SubmissionPage";

vi.mock("@/api/cashout", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/cashout")>();
  return {
    ...actual,
    cashoutApi: {
      ...actual.cashoutApi,
      getSubmission: vi.fn(),
      unsubmitSubmission: vi.fn(),
      completeSubmission: vi.fn(),
      uploadManualDocument: vi.fn(),
    },
  };
});

vi.mock("@/auth/useAuth", () => ({ useAuth: vi.fn() }));

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

const getSubmissionMock = vi.mocked(cashoutApi.getSubmission);
const unsubmitSubmissionMock = vi.mocked(cashoutApi.unsubmitSubmission);
const completeSubmissionMock = vi.mocked(cashoutApi.completeSubmission);
const uploadManualDocumentMock = vi.mocked(cashoutApi.uploadManualDocument);
const useAuthMock = vi.mocked(useAuth);

// jsdom doesn't implement window.scrollTo; completing the cashout calls it.
const scrollToMock = vi.spyOn(window, "scrollTo").mockImplementation(() => {});

const employee: User = {
  id: "user-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "cashier@test.com",
  fullName: "Test User",
  role: "staff",
};

const admin: User = {
  id: "admin-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "admin@test.com",
  fullName: "Test Admin",
  role: "admin",
};

const completedSubmission: CashoutSubmissionDetail = {
  id: "completed-submission",
  createdAt: "2026-07-16T01:00:00Z",
  status: "completed",
  employeeUserId: employee.id,
  submittedAt: "2026-07-16T01:00:00Z",
  businessDate: "2026-07-15",
  completedByUserId: employee.id,
  firstCompletedAt: "2026-07-16T02:00:00Z",
  tipoutDepartments: ["kitchen"],
  updatedAt: "2026-07-16T02:00:00Z",
  employee,
  documents: [],
  data: {
    id: "data-1",
    createdAt: "2026-07-16T02:00:00Z",
    foodNetSales: "800.00",
    drinkNetSales: "400.00",
    totalNetSales: "1200.00",
    cardPaymentTotal: "1234.56",
    cashPaymentTotal: "150.00",
    cardTipTotal: "180.00",
    tipoutDepartments: ["kitchen"],
    barTipoutRate: "0.0500",
    kitchenTipoutRate: "0.0300",
    expoTipoutRate: "0.0100",
    hostTipoutRate: "0.0100",
    barTipout: null,
    kitchenTipout: "24.00",
    expoTipout: null,
    hostTipout: null,
    cashOwedToHouse: null,
    cashOwedToEmployee: "30.00",
    submissionId: "completed-submission",
  },
};

const verifiedSubmission: CashoutSubmissionDetail = {
  ...completedSubmission,
  id: "completed-submission",
  status: "processing",
  completedByUserId: null,
  firstCompletedAt: null,
  tipoutDepartments: null,
  data: null,
  documents: [
    {
      id: "document-1",
      createdAt: "2026-07-16T01:00:00Z",
      contentType: "application/pdf",
      originalFilename: "report.pdf",
      checksumSha256: "abc123",
      uploadedByUserId: employee.id,
      uploadedAt: "2026-07-16T01:00:00Z",
      cashoutSubmissionId: "completed-submission",
      analysis: {
        id: "analysis-1",
        createdAt: "2026-07-16T01:00:00Z",
        provider: "anthropic",
        model: "claude-sonnet-5",
        status: "verified",
        classification: "touchbistro_report",
        classificationConfidence: 0.95,
        schemaName: "TouchBistroReportData",
        extractedDataJson: { total_net_sales: "1500.00" },
        extractionConfidence: 0.9,
        issues: null,
        errorCode: null,
        errorMessage: null,
        completedAt: "2026-07-16T01:01:00Z",
        verifiedDataJson: { total_net_sales: "1500.00" },
        verifiedByUserId: employee.id,
        verifiedAt: "2026-07-16T01:02:00Z",
        cashoutDocumentId: "document-1",
      },
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(
    [{ path: "/cashouts/:submissionId", element: <SubmissionPage /> }],
    { initialEntries: [`/cashouts/${completedSubmission.id}`] },
  );

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function mockViewer(user: User) {
  useAuthMock.mockReturnValue({
    user,
    isLoading: false,
    completeSignIn: vi.fn(),
    logout: vi.fn(async () => undefined),
  });
}

beforeEach(() => {
  getSubmissionMock.mockReset();
  unsubmitSubmissionMock.mockReset();
  completeSubmissionMock.mockReset();
  uploadManualDocumentMock.mockReset();
  useAuthMock.mockReset();
  scrollToMock.mockClear();
  getSubmissionMock.mockResolvedValue(completedSubmission);
  unsubmitSubmissionMock.mockResolvedValue({
    ...completedSubmission,
    status: "processing",
    completedByUserId: null,
  });
  completeSubmissionMock.mockResolvedValue({
    ...verifiedSubmission,
    status: "completed",
  });
  mockViewer(admin);
});

describe("SubmissionPage", () => {
  it("lets an admin unsubmit a completed cashout after a warning", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Unsubmit" }));

    const dialog = screen.getByRole("dialog", { name: "Unsubmit cashout?" });
    expect(
      within(dialog).getByText(
        "This reopens the cashout for editing and removes its reconciled data. Completing it again will regenerate the data.",
      ),
    ).toBeDefined();

    fireEvent.click(within(dialog).getByRole("button", { name: "Unsubmit" }));

    await waitFor(() => expect(unsubmitSubmissionMock).toHaveBeenCalledOnce());
    expect(unsubmitSubmissionMock.mock.calls[0]?.[0]).toBe(
      "completed-submission",
    );
  });

  it("hides Unsubmit from the employee viewing their completed cashout", async () => {
    mockViewer(employee);
    renderPage();

    expect(await screen.findByText("Cashout completed")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Unsubmit" })).toBeNull();
  });

  it("completes with the tipout departments the cashier selected", async () => {
    getSubmissionMock.mockResolvedValue(verifiedSubmission);
    renderPage();

    fireEvent.click(await screen.findByLabelText("Bar"));
    fireEvent.click(screen.getByLabelText("Expo"));
    fireEvent.click(screen.getByRole("button", { name: "Complete cashout" }));

    await waitFor(() => expect(completeSubmissionMock).toHaveBeenCalledOnce());
    expect(completeSubmissionMock.mock.calls[0]).toEqual([
      "completed-submission",
      { tipoutDepartments: ["bar", "expo"] },
    ]);
  });

  it("seeds the tipout checkboxes from the last-completion snapshot", async () => {
    // After an unsubmit the data row is gone, but the submission keeps the
    // snapshot — the form starts from the previous choice.
    getSubmissionMock.mockResolvedValue({
      ...verifiedSubmission,
      tipoutDepartments: ["bar", "kitchen"],
    });
    renderPage();

    expect(
      await screen.findByLabelText<HTMLInputElement>("Bar"),
    ).toHaveProperty("checked", true);
    expect(screen.getByLabelText<HTMLInputElement>("Kitchen")).toHaveProperty(
      "checked",
      true,
    );
    expect(screen.getByLabelText<HTMLInputElement>("Expo")).toHaveProperty(
      "checked",
      false,
    );
    expect(screen.getByLabelText<HTMLInputElement>("Host")).toHaveProperty(
      "checked",
      false,
    );
  });

  it("starts with no tipout checkboxes checked when never completed", async () => {
    getSubmissionMock.mockResolvedValue(verifiedSubmission); // snapshot: null
    renderPage();

    expect(
      await screen.findByLabelText<HTMLInputElement>("Bar"),
    ).toHaveProperty("checked", false);
    for (const label of ["Kitchen", "Expo", "Host"]) {
      expect(screen.getByLabelText<HTMLInputElement>(label)).toHaveProperty(
        "checked",
        false,
      );
    }
  });

  it("scrolls back to the top when completing succeeds", async () => {
    // The completed banner renders at the top of the page, far above the
    // Complete button the cashier just clicked.
    getSubmissionMock.mockResolvedValue(verifiedSubmission);
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "Complete cashout" }),
    );

    await waitFor(() =>
      expect(scrollToMock).toHaveBeenCalledWith({ top: 0, behavior: "smooth" }),
    );
  });

  it("completes with no departments when none is selected", async () => {
    // Tipping out to nobody is a real outcome, not a validation failure.
    getSubmissionMock.mockResolvedValue(verifiedSubmission);
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "Complete cashout" }),
    );

    await waitFor(() => expect(completeSubmissionMock).toHaveBeenCalledOnce());
    expect(completeSubmissionMock.mock.calls[0]?.[1]).toEqual({
      tipoutDepartments: [],
    });
  });

  it("uploads a manually entered document while editable", async () => {
    getSubmissionMock.mockResolvedValue(verifiedSubmission);
    uploadManualDocumentMock.mockResolvedValue({
      ...verifiedSubmission.documents[0]!.analysis!,
      id: "analysis-2",
      provider: null,
      model: null,
      cashoutDocumentId: "document-2",
    });
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "Or enter details manually" }),
    );
    const dialog = screen.getByRole("dialog", {
      name: "Enter document details",
    });

    const file = new File(["img"], "report.jpg", { type: "image/jpeg" });
    fireEvent.change(dialog.querySelector('input[type="file"]')!, {
      target: { files: [file] },
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
    expect(uploadManualDocumentMock).toHaveBeenCalledWith(
      "completed-submission",
      file,
      {
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
      },
    );
    // Success closes the dialog.
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Enter document details" }),
      ).toBeNull(),
    );
  });

  it("hides manual entry on a completed cashout", async () => {
    renderPage(); // completed submission: no upload zone at all

    expect(await screen.findByText("Cashout completed")).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Or enter details manually" }),
    ).toBeNull();
  });

  it("explains a reconciliation conflict when completing fails", async () => {
    // The backend message says what does not add up; the page adds where to
    // go and look for it.
    getSubmissionMock.mockResolvedValue(verifiedSubmission);
    completeSubmissionMock.mockRejectedValue(
      new ApiError(409, {
        kind: "CONFLICT",
        code: "RECONCILE_CARD_PAYMENT_MISMATCH",
        message:
          "The TouchBistro card payments do not match the server summary grand totals. Re-check both before completing.",
      }),
    );
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "Complete cashout" }),
    );

    expect(
      await screen.findByText(/do not match the server summary grand totals/),
    ).toBeDefined();
    expect(
      screen.getByText(/Compare Card payments on the TouchBistro report/),
    ).toBeDefined();
  });

  it("shows the error banner when unsubmitting fails", async () => {
    unsubmitSubmissionMock.mockRejectedValue(
      new ApiError(409, {
        kind: "CONFLICT",
        code: "SUBMISSION_NOT_COMPLETED",
        message: "Only a completed cashout can be unsubmitted.",
      }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Unsubmit" }));
    const dialog = screen.getByRole("dialog", { name: "Unsubmit cashout?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Unsubmit" }));

    // The confirm dialog closed on confirm, so the failure must surface on
    // the page itself.
    expect(
      await screen.findByText("Only a completed cashout can be unsubmitted."),
    ).toBeDefined();
  });
});
