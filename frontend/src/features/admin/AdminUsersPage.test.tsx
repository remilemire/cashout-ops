// frontend/src/features/admin/AdminUsersPage.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import type { User } from "@/api/types";
import { userKeys, usersApi } from "@/api/users";
import { ME_KEY, useAuth } from "@/auth/useAuth";

import { AdminUsersPage } from "./AdminUsersPage";

vi.mock("@/api/users", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/users")>();
  return {
    ...actual,
    usersApi: {
      ...actual.usersApi,
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      promote: vi.fn(),
      demote: vi.fn(),
      remove: vi.fn(),
      transferOwnership: vi.fn(),
    },
  };
});

vi.mock("@/auth/useAuth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/auth/useAuth")>();
  return { ...actual, useAuth: vi.fn() };
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

const listUsersMock = vi.mocked(usersApi.list);
const createMock = vi.mocked(usersApi.create);
const updateMock = vi.mocked(usersApi.update);
const promoteMock = vi.mocked(usersApi.promote);
const demoteMock = vi.mocked(usersApi.demote);
const removeMock = vi.mocked(usersApi.remove);
const transferOwnershipMock = vi.mocked(usersApi.transferOwnership);
const useAuthMock = vi.mocked(useAuth);

const owner: User = {
  id: "owner-1",
  createdAt: "2026-07-14T00:00:00Z",
  email: "owner@test.com",
  fullName: "Owner User",
  role: "owner",
};

const admin: User = {
  id: "admin-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "admin@test.com",
  fullName: "Admin User",
  role: "admin",
};

const staff: User = {
  id: "staff-1",
  createdAt: "2026-07-16T00:00:00Z",
  email: "staff@test.com",
  fullName: "Staff User",
  role: "staff",
};

const otherAdmin: User = {
  id: "admin-2",
  createdAt: "2026-07-15T00:00:00Z",
  email: "other@test.com",
  fullName: "Other Admin",
  role: "admin",
};

function signInAs(user: User) {
  useAuthMock.mockReturnValue({
    user,
    isLoading: false,
    completeSignIn: vi.fn(),
    logout: vi.fn(async () => undefined),
  });
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <AdminUsersPage />
    </QueryClientProvider>,
  );

  return queryClient;
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
  updateMock.mockReset();
  promoteMock.mockReset();
  demoteMock.mockReset();
  removeMock.mockReset();
  transferOwnershipMock.mockReset();
  useAuthMock.mockReset();

  listUsersMock.mockResolvedValue([owner, admin, staff, otherAdmin]);
  createMock.mockResolvedValue({
    id: "staff-2",
    createdAt: "2026-08-09T00:00:00Z",
    email: "new@test.com",
    fullName: "New User",
    role: "staff",
  });
  updateMock.mockResolvedValue({ ...staff, fullName: "Renamed Staff" });
  promoteMock.mockResolvedValue({ ...staff, role: "admin" });
  demoteMock.mockResolvedValue({ ...otherAdmin, role: "staff" });
  removeMock.mockResolvedValue(undefined);
  transferOwnershipMock.mockResolvedValue({ ...admin, role: "owner" });
  signInAs(owner);
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
        ctx: {},
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
  it("offers promote for staff and demote for admins, never a role action for the owner", async () => {
    renderPage();

    expect(
      await screen.findByRole("button", {
        name: "Promote Staff User to admin",
      }),
    ).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Demote Admin User to staff" }),
    ).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Demote Other Admin to staff" }),
    ).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Promote Owner User to admin" }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Demote Owner User to staff" }),
    ).toBeNull();
  });

  it("shows the Owner badge and no role or delete action on the owner's row, even to another admin", async () => {
    signInAs(admin);
    renderPage();

    expect(await screen.findByText("Owner")).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Demote Owner User to staff" }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Delete Owner User" }),
    ).toBeNull();
  });

  it("hides the signed-in admin's own demote and delete", async () => {
    signInAs(admin);
    renderPage();

    expect(
      await screen.findByRole("button", {
        name: "Demote Other Admin to staff",
      }),
    ).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Demote Admin User to staff" }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Delete Admin User" }),
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

describe("AdminUsersPage rename", () => {
  /** Click a row's pencil and return its now-editable name input. */
  async function startRename(name: string, email: string) {
    fireEvent.click(
      await screen.findByRole("button", { name: `Rename ${name}` }),
    );
    return screen.getByLabelText<HTMLInputElement>(`Full name for ${email}`);
  }

  it("offers the rename toggle on every row, the owner's and the signed-in admin's included", async () => {
    signInAs(admin);
    renderPage();

    expect(
      await screen.findByRole("button", { name: "Rename Owner User" }),
    ).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Rename Admin User" }),
    ).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Rename Staff User" }),
    ).toBeDefined();
  });

  it("swaps only the clicked row's name for a prefilled input", async () => {
    renderPage();

    const field = await startRename("Staff User", "staff@test.com");

    expect(field.value).toBe("Staff User");
    // The other rows stay plain text with their toggle intact.
    expect(screen.queryByLabelText("Full name for admin@test.com")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Rename Admin User" }),
    ).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Rename Staff User" }),
    ).toBeNull();
  });

  it("saves the new name and refetches the accounts list", async () => {
    renderPage();

    const field = await startRename("Staff User", "staff@test.com");
    fireEvent.change(field, { target: { value: "  Renamed Staff  " } });
    fireEvent.click(
      screen.getByRole("button", { name: "Save name for staff@test.com" }),
    );

    await waitFor(() => expect(updateMock).toHaveBeenCalledOnce());
    expect(updateMock.mock.calls[0]).toEqual([
      "staff-1",
      { fullName: "Renamed Staff" },
    ]);
    await waitFor(() => expect(listUsersMock).toHaveBeenCalledTimes(2));
    // Back to plain text once saved.
    await waitFor(() =>
      expect(
        screen.queryByLabelText("Full name for staff@test.com"),
      ).toBeNull(),
    );
  });

  it("discards the edit on cancel", async () => {
    renderPage();

    const field = await startRename("Staff User", "staff@test.com");
    fireEvent.change(field, { target: { value: "Discarded" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Cancel renaming Staff User" }),
    );

    expect(screen.queryByLabelText("Full name for staff@test.com")).toBeNull();
    expect(updateMock).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Rename Staff User" }),
    ).toBeDefined();
  });

  it("discards the edit on Escape", async () => {
    renderPage();

    const field = await startRename("Staff User", "staff@test.com");
    fireEvent.change(field, { target: { value: "Discarded" } });
    fireEvent.keyDown(field, { key: "Escape" });

    expect(screen.queryByLabelText("Full name for staff@test.com")).toBeNull();
    expect(updateMock).not.toHaveBeenCalled();
  });

  it("refreshes the session user when the admin renames themselves", async () => {
    signInAs(admin);
    updateMock.mockResolvedValue({ ...admin, fullName: "Renamed Admin" });
    const queryClient = renderPage();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const field = await startRename("Admin User", "admin@test.com");
    fireEvent.change(field, { target: { value: "Renamed Admin" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Save name for admin@test.com" }),
    );

    await waitFor(() => expect(updateMock).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ME_KEY }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: userKeys.list });
  });

  it("leaves the session user alone when renaming someone else", async () => {
    signInAs(admin);
    const queryClient = renderPage();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const field = await startRename("Staff User", "staff@test.com");
    fireEvent.change(field, { target: { value: "Renamed Staff" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Save name for staff@test.com" }),
    );

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: userKeys.list }),
    );
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ME_KEY });
  });

  it("shows the field error when the backend rejects the name", async () => {
    updateMock.mockRejectedValue(
      new ApiError(422, {
        kind: "VALIDATION",
        code: "VALIDATION_FAILED",
        ctx: {},
        issues: [
          {
            code: "string_too_long",
            path: ["fullName"],
            ctx: { maxLength: 200 },
          },
        ],
      }),
    );
    renderPage();

    const field = await startRename("Staff User", "staff@test.com");
    fireEvent.change(field, { target: { value: "x".repeat(201) } });
    fireEvent.click(
      screen.getByRole("button", { name: "Save name for staff@test.com" }),
    );

    expect(
      await screen.findByText("Maximum 200 characters allowed."),
    ).toBeDefined();
    // The row stays in edit mode so the name can be corrected.
    expect(screen.getByLabelText("Full name for staff@test.com")).toBeDefined();
    expect(listUsersMock).toHaveBeenCalledOnce();
  });

  it("never submits a blank name", async () => {
    renderPage();

    const field = await startRename("Staff User", "staff@test.com");
    fireEvent.change(field, { target: { value: "   " } });
    fireEvent.click(
      screen.getByRole("button", { name: "Save name for staff@test.com" }),
    );

    await waitFor(() => expect(updateMock).not.toHaveBeenCalled());
  });
});

describe("AdminUsersPage delete", () => {
  it("confirms the deletion and refetches the accounts list", async () => {
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "Delete Staff User" }),
    );
    expect(screen.getByRole("dialog", { name: "Delete user" })).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(removeMock).toHaveBeenCalledOnce());
    expect(removeMock.mock.calls[0]?.[0]).toBe("staff-1");
    await waitFor(() => expect(listUsersMock).toHaveBeenCalledTimes(2));
  });

  it("closes the dialog and shows the banner when the delete fails", async () => {
    removeMock.mockRejectedValue(
      new ApiError(409, {
        kind: "CONFLICT",
        code: "CONFLICT",
        ctx: {},
      }),
    );
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "Delete Staff User" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(
      await screen.findByText("The request conflicts with the current state."),
    ).toBeDefined();
    // The dialog must not stay open on failure: it would sit on top of the
    // banner and the admin would see nothing happen.
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(listUsersMock).toHaveBeenCalledOnce();
  });
});

describe("AdminUsersPage ownership transfer", () => {
  it("offers transfer to the owner on admin rows only", async () => {
    renderPage();

    expect(
      await screen.findByRole("button", {
        name: "Transfer ownership to Admin User",
      }),
    ).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Transfer ownership to Other Admin" }),
    ).toBeDefined();
    expect(
      screen.queryByRole("button", {
        name: "Transfer ownership to Staff User",
      }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", {
        name: "Transfer ownership to Owner User",
      }),
    ).toBeNull();
  });

  it("never offers transfer to a non-owner admin", async () => {
    signInAs(admin);
    renderPage();

    expect(
      await screen.findByRole("button", {
        name: "Demote Other Admin to staff",
      }),
    ).toBeDefined();
    expect(
      screen.queryByRole("button", { name: /Transfer ownership/ }),
    ).toBeNull();
  });

  it("confirms the transfer and refreshes both the list and the session user", async () => {
    const queryClient = renderPage();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Transfer ownership to Admin User",
      }),
    );
    expect(
      screen.getByRole("dialog", { name: "Transfer ownership" }),
    ).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Transfer" }));

    await waitFor(() => expect(transferOwnershipMock).toHaveBeenCalledOnce());
    expect(transferOwnershipMock.mock.calls[0]?.[0]).toBe("admin-1");
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: userKeys.list }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ME_KEY });
  });
});
