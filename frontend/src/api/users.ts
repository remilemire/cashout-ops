// frontend/src/api/users.ts

import { api } from "./client";
import type { User, UserCreateInput } from "./types";

export const usersApi = {
  /** Every user, newest first (admin only). */
  list: () => api<User[]>("/users"),
  /** Create a user account (admin only). */
  create: (input: UserCreateInput) =>
    api<User>("/users", { method: "POST", json: input }),
  /** Grant a user admin access (admin only). */
  promote: (id: string) =>
    api<User>(`/users/${id}/promote`, { method: "POST" }),
  /** Revoke a user's admin access (admin only). */
  demote: (id: string) => api<User>(`/users/${id}/demote`, { method: "POST" }),
};

/** Central react-query keys so invalidation stays consistent. */
export const userKeys = {
  list: ["users", "list"] as const,
};
