import { Navigate, Outlet, useLocation } from "react-router-dom";

import { isAdminRole } from "@/api/types";
import { FullScreenSpinner } from "@/components/ui";

import { useAuth } from "./useAuth";

/** Everything behind this requires a session; unauthenticated → /login. */
export function RequireAuth() {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <FullScreenSpinner />;
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}

/** Nested under RequireAuth; non-admins are bounced to their home. */
export function RequireAdmin() {
  const { user } = useAuth();

  if (!user || !isAdminRole(user.role)) return <Navigate to="/" replace />;
  return <Outlet />;
}
