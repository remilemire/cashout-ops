// frontend/src/features/admin/AdminUsersPage.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import type { User } from "@/api/types";
import { usersApi } from "@/api/users";
import { useAuth } from "@/auth/useAuth";

import { AdminUsersPage } from "./AdminUsersPage";

vi.mock("@/api/users", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/users")>();
  return {
    ...actual,
    usersApi: {
      ...actual.usersApi,
      list: vi.fn(),
      create: vi.fn(),
      promote: vi.fn(),
      demote: vi.fn(),
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

const listUsersMock = vi.mocked(usersApi.list);
const createMock = vi.mocked(usersApi.create);
const promoteMock = vi.mocked(usersApi.promote);
const demoteMock = vi.mocked(usersApi.demote);
const useAuthMock = vi.mocked(useAuth);

const admin: User = {
  id: "admin-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "admin@test.com",
  fullName: "Admin User",
  isAdmin: true,
};

const staff: User = {
  id: "staff-1",
  createdAt: "2026-07-16T00:00:00Z",
  email: "staff@test.com",
  fullName: "Staff User",
  isAdmin: false,
};

const otherAdmin: User = {
  id: "admin-2",
  createdAt: "2026-07-15T00:00:00Z",
  email: "other@test.com",
  fullName: "Other Admin",
  isAdmin: true,
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <AdminUsersPage />
    </QueryClientProvider>,
  );
}

async function submitNewUser(fullName: string, email: string) {
  fireEvent.change(await screen.findByLabelText("Full name"), {
    target: { value: fullName },
  });
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: email },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add user" }));
}

beforeEach(() => {
  listUsersMock.mockReset();
  createMock.mockReset();
  promoteMock.mockReset();
  demoteMock.mockReset();
  useAuthMock.mockReset();

  listUsersMock.mockResolvedValue([admin, staff, otherAdmin]);
  createMock.mockResolvedValue({
    id: "staff-2",
    createdAt: "2026-08-09T00:00:00Z",
    email: "new@test.com",
    fullName: "New User",
    isAdmin: false,
  });
  promoteMock.mockResolvedValue({ ...staff, isAdmin: true });
  demoteMock.mockResolvedValue({ ...otherAdmin, isAdmin: false });
  useAuthMock.mockReturnValue({
    user: admin,
    isLoading: false,
    completeSignIn: vi.fn(),
    logout: vi.fn(async () => undefined),
  });
});

describe("AdminUsersPage add user", () => {
  it("creates the user and refetches the accounts list", async () => {
    renderPage();

    await submitNewUser("New User", "new@test.com");

    await waitFor(() => expect(createMock).toHaveBeenCalledOnce());
    expect(createMock.mock.calls[0]?.[0]).toEqual({
      email: "new@test.com",
      fullName: "New User",
    });
    await waitFor(() => expect(listUsersMock).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText<HTMLInputElement>("Email").value).toBe("");
    expect(screen.getByLabelText<HTMLInputElement>("Full name").value).toBe("");
  });

  it("shows the error banner when the email is already taken", async () => {
    createMock.mockRejectedValue(
      new ApiError(409, {
        kind: "CONFLICT",
        code: "EMAIL_TAKEN",
        message: "This email is already in use.",
      }),
    );
    renderPage();

    await submitNewUser("New User", "taken@test.com");

    expect(
      await screen.findByText("This email is already in use."),
    ).toBeDefined();
    expect(listUsersMock).toHaveBeenCalledOnce();
  });
});

describe("AdminUsersPage role actions", () => {
  it("offers promote for staff and demote for other admins, never for the signed-in admin", async () => {
    renderPage();

    expect(
      await screen.findByRole("button", {
        name: "Promote Staff User to admin",
      }),
    ).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Demote Other Admin to staff" }),
    ).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Demote Admin User to staff" }),
    ).toBeNull();
  });

  it("confirms and promotes a staff user", async () => {
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Promote Staff User to admin",
      }),
    );
    expect(
      screen.getByRole("dialog", { name: "Promote to admin" }),
    ).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Promote" }));

    await waitFor(() => expect(promoteMock).toHaveBeenCalledOnce());
    expect(promoteMock.mock.calls[0]?.[0]).toBe("staff-1");
    expect(demoteMock).not.toHaveBeenCalled();
  });

  it("confirms and demotes another admin", async () => {
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Demote Other Admin to staff",
      }),
    );
    expect(
      screen.getByRole("dialog", { name: "Demote to staff" }),
    ).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Demote" }));

    await waitFor(() => expect(demoteMock).toHaveBeenCalledOnce());
    expect(demoteMock.mock.calls[0]?.[0]).toBe("admin-2");
    expect(promoteMock).not.toHaveBeenCalled();
  });
});
