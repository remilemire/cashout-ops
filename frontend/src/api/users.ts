// frontend/src/api/users.ts

import { api } from "./client";
import type { User } from "./types";

export const usersApi = {
  /** Every user, newest first (admin only). */
  list: () => api<User[]>("/users"),
};

/** Central react-query keys so invalidation stays consistent. */
export const userKeys = {
  list: ["users", "list"] as const,
};
