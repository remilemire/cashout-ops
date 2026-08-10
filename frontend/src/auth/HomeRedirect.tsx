// frontend/src/auth/HomeRedirect.tsx

import { Navigate } from "react-router-dom";

import { isAdminRole } from "@/api/types";

import { useAuth } from "./useAuth";

/** Role-appropriate landing page. */
export function HomeRedirect() {
  const { user } = useAuth();
  const isAdmin = user !== null && isAdminRole(user.role);
  return <Navigate to={isAdmin ? "/admin/submissions" : "/cashouts"} replace />;
}
