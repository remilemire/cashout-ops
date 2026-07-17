// frontend/src/auth/AuthProvider.tsx

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { LoginInput, RegisterInput, User } from "@/api/types";

const ME_KEY = ["me"] as const;

interface AuthContextValue {
  /** null = definitely signed out; undefined never escapes isLoading. */
  user: User | null;
  isLoading: boolean;
  login: (input: LoginInput) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ME_KEY,
    queryFn: async (): Promise<User | null> => {
      try {
        return await authApi.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const value: AuthContextValue = {
    user: meQuery.data ?? null,
    isLoading: meQuery.isLoading,
    login: async (input) => {
      const user = await authApi.login(input);
      queryClient.setQueryData(ME_KEY, user);
      return user;
    },
    register: async (input) => {
      const user = await authApi.register(input);
      queryClient.setQueryData(ME_KEY, user);
      return user;
    },
    logout: async () => {
      await authApi.logout();
      queryClient.clear();
      queryClient.setQueryData(ME_KEY, null);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
