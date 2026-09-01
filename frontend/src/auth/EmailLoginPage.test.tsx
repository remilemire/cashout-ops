// frontend/src/auth/EmailLoginPage.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { User } from "@/api/types";

import { AuthProvider } from "./AuthProvider";
import { EmailLoginPage } from "./EmailLoginPage";

vi.mock("@/api/auth", () => ({
  authApi: {
    me: vi.fn(),
    startLogin: vi.fn(),
    verifyLoginCode: vi.fn(),
    logout: vi.fn(),
  },
}));

const meMock = vi.mocked(authApi.me);
const startLoginMock = vi.mocked(authApi.startLogin);
const verifyLoginCodeMock = vi.mocked(authApi.verifyLoginCode);

const cashier: User = {
  id: "user-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "cashier@test.com",
  fullName: "Test User",
  role: "staff",
};

const challengeInvalid = new ApiError(401, {
  kind: "UNAUTHORIZED",
  code: "EMAIL_CHALLENGE_INVALID",
  message: "This sign-in code is invalid or has expired.",
});

const rateLimited = new ApiError(
  429,
  {
    kind: "TOO_MANY_REQUESTS",
    code: "RATE_LIMITED",
    message: "Too many attempts. Please wait a moment and try again.",
  },
  300,
);

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "/login/email", element: <EmailLoginPage /> },
      { path: "/", element: <div>Private home</div> },
    ],
    { initialEntries: ["/login/email"] },
  );
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

/** Submit the email form and land on the check-your-email phase. */
async function startChallenge(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText("Email"), "cashier@test.com");
  await user.click(
    screen.getByRole("button", { name: "Email me a sign-in code" }),
  );
  await screen.findByText("Check your email");
}

async function typeCode(user: ReturnType<typeof userEvent.setup>) {
  const inputs = screen.getAllByLabelText(/^Digit \d$/);
  for (const [index, digit] of [..."123456"].entries()) {
    await user.type(inputs[index]!, digit);
  }
}

beforeEach(() => {
  meMock.mockReset();
  startLoginMock.mockReset();
  verifyLoginCodeMock.mockReset();
  meMock.mockRejectedValue(
    new ApiError(401, {
      kind: "UNAUTHORIZED",
      code: "UNAUTHENTICATED",
      message: "Authentication required.",
    }),
  );
  startLoginMock.mockResolvedValue({ challengeId: "challenge-1" });
  verifyLoginCodeMock.mockResolvedValue(cashier);
});

describe("EmailLoginPage", () => {
  it("starts a challenge for the email and shows the check-your-email phase", async () => {
    const user = userEvent.setup();
    renderPage();

    await startChallenge(user);

    expect(startLoginMock).toHaveBeenCalledExactlyOnceWith({
      email: "cashier@test.com",
    });
    expect(screen.getByText("cashier@test.com")).toBeDefined();
    expect(screen.getAllByLabelText(/^Digit \d$/)).toHaveLength(6);
  });

  it("verifies a full code automatically and signs in", async () => {
    const user = userEvent.setup();
    renderPage();

    await startChallenge(user);
    await typeCode(user);

    await waitFor(() =>
      expect(verifyLoginCodeMock).toHaveBeenCalledExactlyOnceWith({
        challengeId: "challenge-1",
        code: "123456",
      }),
    );
    expect(await screen.findByText("Private home")).toBeDefined();
  });

  it("shows wait-time copy when starting a login is rate limited", async () => {
    const user = userEvent.setup();
    startLoginMock.mockRejectedValue(rateLimited);
    renderPage();

    await user.type(await screen.findByLabelText("Email"), "cashier@test.com");
    await user.click(
      screen.getByRole("button", { name: "Email me a sign-in code" }),
    );

    // The Retry-After hint (300s) is surfaced as a rounded-up wait.
    expect(
      await screen.findByText(
        "Too many attempts. Try again in about 5 minutes.",
      ),
    ).toBeDefined();
  });

  it("shows wait-time copy when code verification is rate limited", async () => {
    const user = userEvent.setup();
    verifyLoginCodeMock.mockRejectedValue(rateLimited);
    renderPage();

    await startChallenge(user);
    await typeCode(user);

    expect(
      await screen.findByText(
        "Too many attempts. Try again in about 5 minutes.",
      ),
    ).toBeDefined();
  });

  it("shows the failure and offers a fresh start when the challenge is rejected", async () => {
    const user = userEvent.setup();
    verifyLoginCodeMock.mockRejectedValue(challengeInvalid);
    renderPage();

    await startChallenge(user);
    await typeCode(user);

    // The unified server error is replaced by gentler contextual copy here.
    expect(
      await screen.findByText(
        "That code didn't work. Double-check it, or start over to get a new code.",
      ),
    ).toBeDefined();

    await user.click(screen.getByRole("button", { name: "Start over" }));

    expect(screen.getByLabelText("Email")).toBeDefined();
    expect(screen.queryByText("Check your email")).toBeNull();
  });
});
