// frontend/src/auth/LoginPage.tsx

import { GlassWater, MailCheck } from "lucide-react";
import { useState, type ReactNode, type SyntheticEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { authApi } from "@/api/auth";
import { Button, Card, ErrorBanner, TextField } from "@/components/ui";

import { CodeInput } from "./CodeInput";
import { useAuth } from "./useAuth";

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="mb-5 text-center">
          <span className="bg-accent/15 text-accent-strong mx-auto mb-2 grid size-12 place-items-center rounded-2xl">
            <GlassWater className="size-6" />
          </span>
          <p className="font-semibold">
            <span className="text-accent-strong">Whiskey District</span>{" "}
            Cashouts
          </p>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Set once the email is accepted; its presence selects the code phase. */
interface Challenge {
  challengeId: string;
  email: string;
}

export function LoginPage() {
  const { user, isLoading, completeSignIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Remounts the code input after a rejected code so the boxes clear.
  const [attempt, setAttempt] = useState(0);

  if (!isLoading && user) return <Navigate to="/" replace />;

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const onSubmitEmail = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email"));
    setPending(true);
    setError(null);
    try {
      const { challengeId } = await authApi.startLogin({ email });
      setChallenge({ challengeId, email });
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  };

  const onCodeComplete = async (code: string) => {
    if (!challenge || pending) return;
    setPending(true);
    setError(null);
    try {
      const signedIn = await authApi.verifyLoginCode({
        challengeId: challenge.challengeId,
        code,
      });
      completeSignIn(signedIn);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
      setAttempt((count) => count + 1);
    } finally {
      setPending(false);
    }
  };

  const startOver = () => {
    setChallenge(null);
    setError(null);
    setAttempt(0);
  };

  return (
    <AuthShell>
      <Card>
        {challenge === null ? (
          <>
            <h1 className="mb-1 text-lg font-semibold">Sign in</h1>
            <p className="text-ink-muted mb-4 text-sm">
              Enter your email and we&apos;ll email you a sign-in link.
            </p>
            <form onSubmit={(e) => void onSubmitEmail(e)} className="space-y-3">
              <TextField
                label="Email"
                name="email"
                type="email"
                autoComplete="email"
                required
              />
              <ErrorBanner error={error} />
              <Button type="submit" loading={pending} className="w-full">
                Email me a sign-in link
              </Button>
            </form>
          </>
        ) : (
          <div className="space-y-3">
            <h1 className="text-lg font-semibold">Check your email</h1>
            <p className="text-ink-muted flex items-start gap-2 text-sm">
              <MailCheck className="text-accent-strong mt-0.5 size-4 shrink-0" />
              <span>
                If an account exists for <strong>{challenge.email}</strong>, we
                sent it a sign-in link. Open the link, then enter the code it
                shows you here.
              </span>
            </p>
            <div>
              <span className="mb-1 block text-sm font-medium">
                Sign-in code
              </span>
              <CodeInput
                key={attempt}
                disabled={pending}
                error={error != null}
                onComplete={(code) => void onCodeComplete(code)}
              />
            </div>
            <ErrorBanner error={error} />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={startOver}
              disabled={pending}
            >
              Start over
            </Button>
          </div>
        )}
      </Card>
    </AuthShell>
  );
}
