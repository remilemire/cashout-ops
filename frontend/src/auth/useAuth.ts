// frontend/src/auth/useAuth.ts

import { createContext, useContext } from "react";

import type { User } from "@/api/types";

export interface AuthContextValue {
  /** null = definitely signed out; undefined never escapes isLoading. */
  user: User | null;
  isLoading: boolean;
  /** Record the user returned by a completed login as the session user. */
  completeSignIn: (user: User) => void;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
