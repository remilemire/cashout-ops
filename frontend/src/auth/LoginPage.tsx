// frontend/src/auth/LoginPage.tsx

import { Mail } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { Button, Card, ErrorBanner } from "@/components/ui";
import { hardNavigate } from "@/lib/navigation";

import { AuthShell } from "./AuthShell";
import { useAuth } from "./useAuth";

/**
 * Sign-in method chooser: passwordless email, or Google. A failed OAuth
 * callback redirects back here with `?error={code}`, rendered as a banner.
 * Only a disabled issuer — decided before the browser leaves for Google —
 * gets its own message; every other code shares one, because the backend
 * deliberately reports one code for every failure past that point.
 */
export function LoginPage() {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Where to land after sign-in, seeded by the guard's redirect state. For
  // OAuth it rides the start URL and is stored (and sanitized) server-side.
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const oauthError = new URLSearchParams(location.search).get("error");

  if (!isLoading && user) return <Navigate to="/" replace />;

  return (
    <AuthShell>
      <Card>
        <h1 className="mb-1 text-lg font-semibold">Sign in</h1>
        <p className="text-ink-muted mb-4 text-sm">
          Choose how you want to sign in.
        </p>
        <div className="space-y-3">
          <ErrorBanner
            error={oauthError}
            message={
              oauthError === "OAUTH_ISSUER_NOT_ENABLED"
                ? "Google sign-in isn't available right now. Continue with email instead."
                : "This Google account can't be used to access Cashout. Try a different account or contact an administrator."
            }
          />
          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={() =>
              // Forward the guard's `from` state so the redirect-back survives
              // the hop through the method chooser.
              navigate("/login/email", { state: location.state })
            }
          >
            <Mail className="size-4" />
            Continue with email
          </Button>
          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={() =>
              // A top-level navigation, not a fetch: the backend answers with
              // a redirect to Google, which XHR could never follow.
              hardNavigate(
                `/api/auth/oauth/google/start?redirect_to=${encodeURIComponent(from)}`,
              )
            }
          >
            <GoogleIcon className="size-4" />
            Continue with Google
          </Button>
        </div>
      </Card>
    </AuthShell>
  );
}

// Google's brand mark (lucide ships no brand icons). Brand colors on purpose,
// not theme tokens — the logo must not restyle with the theme.
function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.46c-.28 1.5-1.13 2.77-2.4 3.62v3.01h3.88c2.27-2.09 3.58-5.17 3.58-8.82z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.88-3.01c-1.07.72-2.45 1.15-4.06 1.15-3.13 0-5.78-2.11-6.72-4.95H1.27v3.11C3.25 21.31 7.31 24 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.28 14.28A7.2 7.2 0 0 1 4.9 12c0-.79.14-1.56.38-2.28V6.61H1.27A12 12 0 0 0 0 12c0 1.94.46 3.77 1.27 5.39l4.01-3.11z"
      />
      <path
        fill="#EA4335"
        d="M12 4.77c1.76 0 3.34.61 4.59 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0 7.31 0 3.25 2.69 1.27 6.61l4.01 3.11C6.22 6.88 8.87 4.77 12 4.77z"
      />
    </svg>
  );
}
