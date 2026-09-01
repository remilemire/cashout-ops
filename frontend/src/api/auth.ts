// frontend/src/api/auth.ts

import { api } from "./client";
import type {
  LoginStart,
  LoginStartInput,
  User,
  VerifyLoginCodeInput,
} from "./types";

export const authApi = {
  me: () => api<User>("/users/me"),
  /** Begin a passwordless login; always 202, even for unknown emails. */
  startLogin: (input: LoginStartInput) =>
    api<LoginStart>("/auth/email-challenges", { method: "POST", json: input }),
  /** Complete the login with the emailed code; sets the session cookies. */
  verifyLoginCode: (input: VerifyLoginCodeInput) =>
    api<User>("/auth/email-challenges/verify-code", {
      method: "POST",
      json: input,
    }),
  logout: () => api<void>("/auth/logout", { method: "POST" }),
};
