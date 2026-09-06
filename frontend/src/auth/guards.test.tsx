// frontend/src/auth/guards.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { User } from "@/api/types";

import { AuthProvider } from "./AuthProvider";
import { RequireAdmin, RequireAuth } from "./guards";

vi.mock("@/api/auth", () => ({
  authApi: {
    me: vi.fn(),
    startLogin: vi.fn(),
    verifyLoginCode: vi.fn(),
    logout: vi.fn(),
  },
}));

const meMock = vi.mocked(authApi.me);

const cashier: User = {
  id: "user-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "cashier@test.com",
  fullName: "Test User",
  role: "staff",
};

function renderGuarded() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "/login", element: <div>Login page</div> },
      {
        element: <RequireAuth />,
        children: [{ path: "/", element: <div>Private home</div> }],
      },
    ],
    { initialEntries: ["/"] },
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function renderAdminGuarded() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "/", element: <div>Home page</div> },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <RequireAdmin />,
            children: [{ path: "/admin", element: <div>Admin area</div> }],
          },
        ],
      },
    ],
    { initialEntries: ["/admin"] },
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  meMock.mockReset();
});

describe("RequireAuth", () => {
  it("redirects signed-out visitors to the login page", async () => {
    meMock.mockRejectedValue(
      new ApiError(401, {
        kind: "UNAUTHORIZED",
        code: "UNAUTHENTICATED",
        ctx: {},
      }),
    );

    renderGuarded();

    expect(await screen.findByText("Login page")).toBeDefined();
  });

  it("renders the protected content for a signed-in user", async () => {
    meMock.mockResolvedValue(cashier);

    renderGuarded();

    expect(await screen.findByText("Private home")).toBeDefined();
  });
});

describe("RequireAdmin", () => {
  it("bounces staff back to their home", async () => {
    meMock.mockResolvedValue(cashier);

    renderAdminGuarded();

    expect(await screen.findByText("Home page")).toBeDefined();
  });

  it("renders the admin area for an admin", async () => {
    meMock.mockResolvedValue({ ...cashier, role: "admin" });

    renderAdminGuarded();

    expect(await screen.findByText("Admin area")).toBeDefined();
  });

  it("renders the admin area for the owner", async () => {
    meMock.mockResolvedValue({ ...cashier, role: "owner" });

    renderAdminGuarded();

    expect(await screen.findByText("Admin area")).toBeDefined();
  });
});
