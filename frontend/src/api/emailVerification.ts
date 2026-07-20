// frontend/src/api/emailVerification.ts

import { api } from "./client";
import type { User, VerifyEmailInput } from "./types";

/** The signed-in (unverified) user confirms or re-requests their email code. */
export const emailVerificationApi = {
  /** Confirm the emailed code; returns the now-verified user. */
  verify: (input: VerifyEmailInput) =>
    api<User>("/email-verification/verify", { method: "POST", json: input }),
  /** Email a fresh code (rate-limited); the previous code is invalidated. */
  resend: () => api<void>("/email-verification/resend", { method: "POST" }),
};
