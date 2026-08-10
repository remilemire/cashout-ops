// frontend/src/auth/LoginPage.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";

import { AuthProvider } from "./AuthProvider";
import { LoginPage } from "./LoginPage";

vi.mock("@/api/auth", () => ({
  authApi: {
    me: vi.fn(),
    startLogin: vi.fn(),
    verifyLoginLink: vi.fn(),
    verifyLoginCode: vi.fn(),
    logout: vi.fn(),
  },
}));

const meMock = vi.mocked(authApi.me);

function renderPage(initialState?: { from?: string }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/login/email", element: <div>Email login page</div> },
    ],
    {
      initialEntries: [{ pathname: "/login", state: initialState ?? null }],
    },
  );
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(() => {
  meMock.mockReset();
  meMock.mockRejectedValue(
    new ApiError(401, {
      kind: "UNAUTHORIZED",
      code: "UNAUTHENTICATED",
      message: "Authentication required.",
    }),
  );
});

describe("LoginPage", () => {
  it("offers email sign-in as a method", async () => {
    renderPage();

    expect(
      await screen.findByRole("button", { name: "Continue with email" }),
    ).toBeDefined();
  });

  it("navigates to the email flow, forwarding the redirect-back state", async () => {
    const user = userEvent.setup();
    const router = renderPage({ from: "/cashouts" });

    await user.click(
      await screen.findByRole("button", { name: "Continue with email" }),
    );

    expect(await screen.findByText("Email login page")).toBeDefined();
    expect(router.state.location.pathname).toBe("/login/email");
    expect(router.state.location.state).toEqual({ from: "/cashouts" });
  });
});
