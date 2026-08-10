// frontend/src/features/cashout/CashoutsPage.test.tsx

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
  fullName: "Test User",
  role: "staff",
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
    completeSignIn: vi.fn(),
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

  it("keeps submissions distinct when the truncated ids collide", async () => {
    // The visible "#xxxxxxxx" label truncates the UUID to 8 chars; rows and
    // actions must still key off the full id.
    const twin = (suffix: string): CashoutSubmissionListItem => ({
      id: `aaaaaaaa-0000-4000-8000-00000000000${suffix}`,
      createdAt: "2026-07-17T01:00:00Z",
      status: "PROCESSING",
      submittedByUserId: user.id,
      submittedAt: "2026-07-17T01:00:00Z",
      submittedBy: user,
    });
    listSubmissionsMock.mockResolvedValue([twin("1"), twin("2")]);
    renderPage();

    // Both rows render despite sharing the same truncated label.
    expect(await screen.findAllByText("#aaaaaaaa")).toHaveLength(2);
    const rowLinks = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(rowLinks).toContain(
      "/cashouts/aaaaaaaa-0000-4000-8000-000000000001",
    );
    expect(rowLinks).toContain(
      "/cashouts/aaaaaaaa-0000-4000-8000-000000000002",
    );

    // Cancelling the second row targets its full UUID, not its twin's.
    fireEvent.click(screen.getAllByRole("button", { name: "Cancel" })[1]!);
    fireEvent.click(screen.getByRole("button", { name: "Cancel cashout" }));

    await waitFor(() => expect(cancelSubmissionMock).toHaveBeenCalledOnce());
    expect(cancelSubmissionMock.mock.calls[0]?.[0]).toBe(
      "aaaaaaaa-0000-4000-8000-000000000002",
    );
  });
});
