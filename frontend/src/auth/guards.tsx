// frontend/src/auth/guards.tsx

import { Navigate, Outlet, useLocation } from "react-router-dom";

import { FullScreenSpinner } from "@/components/ui";

import { useAuth } from "./AuthProvider";
import { EmailVerificationGate } from "./EmailVerificationGate";

/** Everything behind this requires a session; unauthenticated → /login. */
export function RequireAuth() {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <FullScreenSpinner />;
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return (
    <EmailVerificationGate user={user}>
      <Outlet />
    </EmailVerificationGate>
  );
}

/** Nested under RequireAuth; non-admins are bounced to their home. */
export function RequireAdmin() {
  const { user } = useAuth();

  if (user?.role !== "ADMIN") return <Navigate to="/" replace />;
  return <Outlet />;
}
