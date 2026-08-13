// frontend/src/auth/LoginPage.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { hardNavigate } from "@/lib/navigation";

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

// jsdom's window.location is unforgeable, so the OAuth button navigates
// through this seam instead.
vi.mock("@/lib/navigation", () => ({
  hardNavigate: vi.fn(),
}));

const meMock = vi.mocked(authApi.me);
const hardNavigateMock = vi.mocked(hardNavigate);

function renderPage(options?: { from?: string; search?: string }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/login/email", element: <div>Email login page</div> },
    ],
    {
      initialEntries: [
        {
          pathname: "/login",
          search: options?.search ?? "",
          state: options?.from ? { from: options.from } : null,
        },
      ],
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
  hardNavigateMock.mockReset();
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

  it("offers Google sign-in as a method", async () => {
    renderPage();

    expect(
      await screen.findByRole("button", { name: "Continue with Google" }),
    ).toBeDefined();
  });

  it("starts the Google flow with the redirect-back path", async () => {
    const user = userEvent.setup();
    renderPage({ from: "/cashouts" });

    await user.click(
      await screen.findByRole("button", { name: "Continue with Google" }),
    );

    expect(hardNavigateMock).toHaveBeenCalledExactlyOnceWith(
      "/api/auth/oauth/google/start?redirect_to=%2Fcashouts",
    );
  });

  it("defaults the redirect-back path to home", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Continue with Google" }),
    );

    expect(hardNavigateMock).toHaveBeenCalledExactlyOnceWith(
      "/api/auth/oauth/google/start?redirect_to=%2F",
    );
  });

  it("shows the account-not-found callback error", async () => {
    renderPage({ search: "?error=OAUTH_ACCOUNT_NOT_FOUND" });

    expect(
      await screen.findByText(
        "That Google account doesn't match any account here. Ask an admin to create your account, or sign in with email.",
      ),
    ).toBeDefined();
  });

  it("shows a generic message for other callback errors", async () => {
    renderPage({ search: "?error=OAUTH_FLOW_INVALID" });

    expect(
      await screen.findByText("Google sign-in didn't complete. Please try again."),
    ).toBeDefined();
  });

  it("shows no error banner without a callback error", async () => {
    renderPage();

    await screen.findByRole("button", { name: "Continue with email" });
    expect(screen.queryByText(/sign-in didn't complete/)).toBeNull();
  });
});
