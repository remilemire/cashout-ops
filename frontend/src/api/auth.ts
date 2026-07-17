// frontend/src/api/auth.ts

import { api } from "./client";
import type { LoginInput, RegisterInput, User } from "./types";

export const authApi = {
  me: () => api<User>("/users/me"),
  login: (input: LoginInput) =>
    api<User>("/auth/login", { method: "POST", json: input }),
  register: (input: RegisterInput) =>
    api<User>("/auth/register", { method: "POST", json: input }),
  logout: () => api<void>("/auth/logout", { method: "POST" }),
};
