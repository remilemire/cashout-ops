// frontend/src/auth/LoginLinkPage.tsx

import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { authApi } from "@/api/auth";
import { Card, Spinner } from "@/components/ui";

import { AuthShell } from "./LoginPage";

/**
 * Landing page for the emailed magic link (`/login/link?challenge=…&token=…`),
 * possibly opened on another device. Redeeming the link only reveals the
 * 6-digit code; no session is created here — login completes in the tab
 * where it started.
 */
export function LoginLinkPage() {
  const [searchParams] = useSearchParams();
  const challenge = searchParams.get("challenge");
  const token = searchParams.get("token");
  const hasParams = challenge !== null && token !== null;

  const linkQuery = useQuery({
    queryKey: ["login-link", challenge],
    queryFn: () =>
      authApi.verifyLoginLink({ challengeId: challenge!, token: token! }),
    enabled: hasParams,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  return (
    <AuthShell>
      <Card className="text-center">
        {!hasParams || linkQuery.isError ? (
          <div className="space-y-3">
            <p className="font-medium">
              This sign-in link is invalid or has expired.
            </p>
            <p className="text-ink-muted text-sm">
              <Link
                to="/login"
                className="text-accent-strong font-medium hover:underline"
              >
                Go back to sign in
              </Link>
            </p>
          </div>
        ) : linkQuery.data === undefined ? (
          <div className="flex justify-center py-4">
            <Spinner className="size-8" />
          </div>
        ) : (
          <div className="space-y-3">
            <h1 className="text-lg font-semibold">Your sign-in code</h1>
            <p className="text-3xl font-bold tracking-widest tabular-nums">
              {linkQuery.data.code}
            </p>
            <p className="text-ink-muted text-sm">
              Enter this code in the tab where you started signing in, then
              close this page.
            </p>
          </div>
        )}
      </Card>
    </AuthShell>
  );
}
