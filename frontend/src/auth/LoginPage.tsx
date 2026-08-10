// frontend/src/auth/LoginPage.tsx

import { Mail } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { Button, Card } from "@/components/ui";

import { AuthShell } from "./AuthShell";
import { useAuth } from "./useAuth";

/**
 * Sign-in method chooser. Email is the only method today; future providers
 * (e.g. OAuth) slot in as additional options on this card.
 */
export function LoginPage() {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!isLoading && user) return <Navigate to="/" replace />;

  return (
    <AuthShell>
      <Card>
        <h1 className="mb-1 text-lg font-semibold">Sign in</h1>
        <p className="text-ink-muted mb-4 text-sm">
          Choose how you want to sign in.
        </p>
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
      </Card>
    </AuthShell>
  );
}
