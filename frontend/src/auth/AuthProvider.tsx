// frontend/src/auth/AuthProvider.tsx

import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { User } from "@/api/types";

import { AuthContext, type AuthContextValue } from "./useAuth";

const ME_KEY = ["me"] as const;

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
      try {
        await authApi.logout();
      } catch {
        // Signing out is best-effort on the client: even if the request
        // fails, we still drop local auth state so guards send us to /login.
      }
      // Mark signed-out first so route guards observe `null` immediately, then
      // drop the rest of the cached per-user data without refetching `me`.
      queryClient.setQueryData(ME_KEY, null);
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== ME_KEY[0],
      });
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
