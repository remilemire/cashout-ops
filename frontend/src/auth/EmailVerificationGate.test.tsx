// frontend/src/auth/EmailVerificationGate.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { emailVerificationApi } from "@/api/emailVerification";
import type { User } from "@/api/types";

import { EmailVerificationGate } from "./EmailVerificationGate";
import { AuthContext, type AuthContextValue } from "./useAuth";

vi.mock("@/api/emailVerification", () => ({
  emailVerificationApi: {
    verify: vi.fn(),
    resend: vi.fn(),
  },
}));

const verifyMock = vi.mocked(emailVerificationApi.verify);
const resendMock = vi.mocked(emailVerificationApi.resend);

const unverified: User = {
  id: "user-1",
  createdAt: "2026-07-17T00:00:00Z",
  email: "cashier@test.com",
  fullName: "Test User",
  isAdmin: false,
  isActive: true,
  emailVerifiedAt: null,
};

const auth: AuthContextValue = {
  user: unverified,
  isLoading: false,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
};

function renderGate() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth}>
        <EmailVerificationGate user={unverified}>
          <div>Behind the gate</div>
        </EmailVerificationGate>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
  return screen.getAllByLabelText(/^Digit \d$/) as HTMLInputElement[];
}

beforeEach(() => {
  verifyMock.mockReset();
  resendMock.mockReset();
  verifyMock.mockResolvedValue({
    ...unverified,
    emailVerifiedAt: "2026-07-17T00:00:00Z",
  });
  resendMock.mockResolvedValue(undefined);
});

describe("VerifyEmailDialog code inputs", () => {
  it("renders one input per digit", () => {
    const inputs = renderGate();
    expect(inputs).toHaveLength(6);
  });

  it("ignores non-digit characters", async () => {
    const user = userEvent.setup();
    const inputs = renderGate();

    await user.click(inputs[0]!);
    await user.keyboard("a");
    expect(inputs[0]!.value).toBe("");

    await user.keyboard("5");
    expect(inputs[0]!.value).toBe("5");
    expect(verifyMock).not.toHaveBeenCalled();
  });

  it("advances focus to the next box after a digit is entered", async () => {
    const user = userEvent.setup();
    const inputs = renderGate();

    await user.click(inputs[0]!);
    await user.keyboard("1");

    expect(inputs[0]!.value).toBe("1");
    expect(document.activeElement).toBe(inputs[1]);
  });

  it("submits automatically once all six digits are entered", async () => {
    const user = userEvent.setup();
    const inputs = renderGate();

    // Enter one digit per box, awaiting each keystroke so the boxes re-render
    // between entries (mirroring how a person types the code in).
    for (const [index, digit] of [..."123456"].entries()) {
      await user.type(inputs[index]!, digit);
    }

    // react-query passes a context object as the second argument to the
    // mutationFn, so match the payload and allow anything after it.
    await waitFor(() =>
      expect(verifyMock).toHaveBeenCalledWith(
        { code: "123456" },
        expect.anything(),
      ),
    );
    expect(verifyMock).toHaveBeenCalledTimes(1);
    expect(inputs[5]!.value).toBe("6");
  });
});
