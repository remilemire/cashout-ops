// frontend/src/auth/guards.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { User } from "@/api/types";

import { AuthProvider } from "./AuthProvider";
import { RequireAuth } from "./guards";

vi.mock("@/api/auth", () => ({
  authApi: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
}));

const meMock = vi.mocked(authApi.me);

const cashier: User = {
  id: "user-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "cashier@test.com",
  firstName: "Test",
  lastName: "User",
  role: "CASHIER",
  isActive: true,
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

beforeEach(() => {
  meMock.mockReset();
});

describe("RequireAuth", () => {
  it("redirects signed-out visitors to the login page", async () => {
    meMock.mockRejectedValue(
      new ApiError(401, {
        kind: "UNAUTHORIZED",
        code: "UNAUTHENTICATED",
        message: "Authentication required.",
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
