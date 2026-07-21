// frontend/src/auth/useAuth.ts

import { createContext, useContext } from "react";

import type { LoginInput, RegisterInput, User } from "@/api/types";

export interface AuthContextValue {
  /** null = definitely signed out; undefined never escapes isLoading. */
  user: User | null;
  isLoading: boolean;
  login: (input: LoginInput) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
