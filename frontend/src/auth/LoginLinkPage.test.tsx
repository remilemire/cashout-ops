// frontend/src/auth/LoginLinkPage.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";

import { LoginLinkPage } from "./LoginLinkPage";

vi.mock("@/api/auth", () => ({
  authApi: {
    me: vi.fn(),
    startLogin: vi.fn(),
    verifyLoginLink: vi.fn(),
    verifyLoginCode: vi.fn(),
    logout: vi.fn(),
  },
}));

const verifyLoginLinkMock = vi.mocked(authApi.verifyLoginLink);

function renderPage(search: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [{ path: "/login/link", element: <LoginLinkPage /> }],
    { initialEntries: [`/login/link${search}`] },
  );
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  verifyLoginLinkMock.mockReset();
});

describe("LoginLinkPage", () => {
  it("redeems the link and displays the sign-in code", async () => {
    verifyLoginLinkMock.mockResolvedValue({ code: "123456" });

    renderPage("?challenge=challenge-1&token=token-1");

    expect(await screen.findByText("123456")).toBeDefined();
    expect(verifyLoginLinkMock).toHaveBeenCalledExactlyOnceWith({
      challengeId: "challenge-1",
      token: "token-1",
    });
  });

  it("shows the invalid-link state when the backend rejects the link", async () => {
    verifyLoginLinkMock.mockRejectedValue(
      new ApiError(401, {
        kind: "UNAUTHORIZED",
        code: "LOGIN_CHALLENGE_INVALID",
        message: "This sign-in link is invalid or has expired.",
      }),
    );

    renderPage("?challenge=challenge-1&token=token-1");

    expect(
      await screen.findByText("This sign-in link is invalid or has expired."),
    ).toBeDefined();
    expect(
      screen.getByRole("link", { name: "Go back to sign in" }),
    ).toBeDefined();
  });

  it("shows the invalid-link state without calling the API when params are missing", () => {
    renderPage("?challenge=challenge-1");

    expect(
      screen.getByText("This sign-in link is invalid or has expired."),
    ).toBeDefined();
    expect(verifyLoginLinkMock).not.toHaveBeenCalled();
  });
});
