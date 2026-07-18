import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cashoutApi } from "@/api/cashout";
import type { CashoutSubmissionListItem, User } from "@/api/types";
import { useAuth } from "@/auth/useAuth";

import { CashoutsPage } from "./CashoutsPage";

vi.mock("@/api/cashout", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/cashout")>();
  return {
    ...actual,
    cashoutApi: {
      ...actual.cashoutApi,
      listSubmissions: vi.fn(),
      cancelSubmission: vi.fn(),
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

const listSubmissionsMock = vi.mocked(cashoutApi.listSubmissions);
const cancelSubmissionMock = vi.mocked(cashoutApi.cancelSubmission);
const useAuthMock = vi.mocked(useAuth);

const user: User = {
  id: "user-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "cashier@test.com",
  firstName: "Test",
  lastName: "User",
  role: "CASHIER",
  isActive: true,
};

const submissions: CashoutSubmissionListItem[] = [
  {
    id: "processing-submission",
    createdAt: "2026-07-17T01:00:00Z",
    status: "PROCESSING",
    submittedByUserId: user.id,
    submittedAt: "2026-07-17T01:00:00Z",
    submittedBy: user,
  },
  {
    id: "completed-submission",
    createdAt: "2026-07-16T01:00:00Z",
    status: "COMPLETED",
    submittedByUserId: user.id,
    submittedAt: "2026-07-16T01:00:00Z",
    submittedBy: user,
  },
];

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(
    [{ path: "/cashouts", element: <CashoutsPage /> }],
    { initialEntries: ["/cashouts"] },
  );

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listSubmissionsMock.mockReset();
  cancelSubmissionMock.mockReset();
  useAuthMock.mockReset();
  listSubmissionsMock.mockResolvedValue(submissions);
  cancelSubmissionMock.mockResolvedValue(undefined);
  useAuthMock.mockReturnValue({
    user,
    isLoading: false,
    login: vi.fn(async () => user),
    register: vi.fn(async () => user),
    logout: vi.fn(async () => undefined),
  });
});

describe("CashoutsPage", () => {
  it("only offers cancellation for incomplete submissions", async () => {
    renderPage();

    expect(await screen.findByText("#processi")).toBeDefined();
    expect(screen.getByText("#complete")).toBeDefined();
    expect(screen.getAllByRole("button", { name: "Cancel" })).toHaveLength(1);
  });

  it("confirms and cancels an incomplete submission", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(
      screen.getByRole("dialog", { name: "Cancel cashout?" }),
    ).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Cancel cashout" }));

    await waitFor(() => expect(cancelSubmissionMock).toHaveBeenCalledOnce());
    expect(cancelSubmissionMock.mock.calls[0]?.[0]).toBe(
      "processing-submission",
    );
  });
});
