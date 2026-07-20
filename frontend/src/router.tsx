// frontend/src/router.tsx

import { createBrowserRouter } from "react-router-dom";

import { RequireAdmin, RequireAuth } from "@/auth/guards";
import { HomeRedirect } from "@/auth/HomeRedirect";
import { LoginPage } from "@/auth/LoginPage";
import { RegisterPage } from "@/auth/RegisterPage";
import { EmptyState } from "@/components/ui";
import { AdminDataPage } from "@/features/admin/AdminDataPage";
import { AdminSubmissionsPage } from "@/features/admin/AdminSubmissionsPage";
import { AdminUsersPage } from "@/features/admin/AdminUsersPage";
import { CashoutsPage } from "@/features/cashout/CashoutsPage";
import { NewCashoutPage } from "@/features/cashout/NewCashoutPage";
import { SubmissionPage } from "@/features/cashout/SubmissionPage";
import { AppLayout } from "@/layout/AppLayout";

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
          { path: "/cashouts/new", element: <NewCashoutPage /> },
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
              { path: "/admin/users", element: <AdminUsersPage /> },
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
