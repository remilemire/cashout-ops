// frontend/src/router.tsx

import { createBrowserRouter, Navigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { RequireAdmin, RequireAuth } from "@/auth/guards";
import { LoginPage } from "@/auth/LoginPage";
import { RegisterPage } from "@/auth/RegisterPage";
import { EmptyState } from "@/components/ui";
import { AdminDataPage } from "@/features/admin/AdminDataPage";
import { AdminSubmissionsPage } from "@/features/admin/AdminSubmissionsPage";
import { CashoutsPage } from "@/features/cashout/CashoutsPage";
import { SubmissionPage } from "@/features/cashout/SubmissionPage";
import { AppLayout } from "@/layout/AppLayout";

/** Role-appropriate landing page. */
function HomeRedirect() {
  const { user } = useAuth();
  return (
    <Navigate
      to={user?.role === "ADMIN" ? "/admin/submissions" : "/cashouts"}
      replace
    />
  );
}

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <HomeRedirect /> },
          { path: "/cashouts", element: <CashoutsPage /> },
          { path: "/cashouts/:submissionId", element: <SubmissionPage /> },
          {
            element: <RequireAdmin />,
            children: [
              { path: "/admin/submissions", element: <AdminSubmissionsPage /> },
              // The admin detail reuses the cashier view, which renders
              // read-only for submissions the viewer doesn't own.
              {
                path: "/admin/submissions/:submissionId",
                element: <SubmissionPage />,
              },
              { path: "/admin/data", element: <AdminDataPage /> },
            ],
          },
          {
            path: "*",
            element: (
              <EmptyState title="Page not found" hint="Check the address." />
            ),
          },
        ],
      },
    ],
  },
]);
