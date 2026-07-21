import { Navigate } from "react-router-dom";

import { useAuth } from "./useAuth";

/** Role-appropriate landing page. */
export function HomeRedirect() {
  const { user } = useAuth();
  return (
    <Navigate to={user?.isAdmin ? "/admin/submissions" : "/cashouts"} replace />
  );
}
