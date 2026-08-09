// frontend/src/api/auth.ts

import { api } from "./client";
import type {
  LoginCode,
  LoginStart,
  LoginStartInput,
  User,
  VerifyLoginCodeInput,
  VerifyLoginLinkInput,
} from "./types";

export const authApi = {
  me: () => api<User>("/users/me"),
  /** Begin a passwordless login; always 202, even for unknown emails. */
  startLogin: (input: LoginStartInput) =>
    api<LoginStart>("/auth/login", { method: "POST", json: input }),
  /** Redeem the emailed magic link for the 6-digit code (repeatable). */
  verifyLoginLink: (input: VerifyLoginLinkInput) =>
    api<LoginCode>("/auth/login/verify-link", { method: "POST", json: input }),
  /** Complete the login with the code; sets the session cookies. */
  verifyLoginCode: (input: VerifyLoginCodeInput) =>
    api<User>("/auth/login/verify-code", { method: "POST", json: input }),
  logout: () => api<void>("/auth/logout", { method: "POST" }),
};
