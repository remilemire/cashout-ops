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
const useAuthMock = vi.mocked(useAuth);

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
  completedByUserId: employee.id,
  firstCompletedByUserId: employee.id,
  updatedAt: "2026-07-16T02:00:00Z",
  employee,
  documents: [],
  data: {
    id: "data-1",
    createdAt: "2026-07-16T02:00:00Z",
    dailyTipout: null,
    netTotal: null,
    cashTotal: null,
    cardTotal: null,
    submissionId: "completed-submission",
  },
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
  useAuthMock.mockReset();
  getSubmissionMock.mockResolvedValue(completedSubmission);
  unsubmitSubmissionMock.mockResolvedValue({
    ...completedSubmission,
    status: "processing",
    completedByUserId: null,
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
