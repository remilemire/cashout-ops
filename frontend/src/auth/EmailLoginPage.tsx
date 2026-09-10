import { useState, type SyntheticEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button, Card, ErrorBanner, TextField } from "@/components/ui";

import { AuthShell } from "./AuthShell";
import { CodeInput } from "./CodeInput";
import { useAuth } from "./useAuth";

/** Set once the email is accepted; its presence selects the code phase. */
interface Challenge {
  challengeId: string;
  email: string;
}

/** Friendlier 429 copy: name the wait when the server hinted at one. */
function rateLimitedCopy(retryAfterSeconds: number | null): string {
  if (retryAfterSeconds == null) {
    return "Too many attempts. Please wait a moment and try again.";
  }
  const minutes = Math.max(1, Math.ceil(retryAfterSeconds / 60));
  const wait = minutes === 1 ? "about a minute" : `about ${minutes} minutes`;
  return `Too many attempts. Try again in ${wait}.`;
}

export function EmailLoginPage() {
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

  // Rate limiting can hit either phase; both banners share this override.
  const rateLimitMessage =
    error instanceof ApiError && error.code === "RATE_LIMITED"
      ? rateLimitedCopy(error.retryAfterSeconds)
      : undefined;

  // The server's unified challenge error covers mistyped, superseded, and
  // expired codes alike; on this screen a gentler nudge fits all of them.
  const codeErrorMessage =
    error instanceof ApiError && error.code === "EMAIL_CHALLENGE_INVALID"
      ? "That code didn't work. Double-check it, or start over to get a new code."
      : rateLimitMessage;

  return (
    <AuthShell>
      <Card>
        {challenge === null ? (
          <>
            <h1 className="mb-1 text-lg font-semibold">Sign in with email</h1>
            <p className="text-ink-muted mb-4 text-sm">
              Enter your email and we&apos;ll email you a one-time sign-in code.
            </p>
            <form onSubmit={(e) => void onSubmitEmail(e)} className="space-y-3">
              <TextField
                label="Email"
                name="email"
                type="email"
                autoComplete="email"
                required
              />
              <ErrorBanner error={error} message={rateLimitMessage} />
              <Button type="submit" loading={pending} className="w-full">
                Email me a sign-in code
              </Button>
              <div className="text-center">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-ink-muted hover:text-ink min-h-0! py-1"
                  disabled={pending}
                  onClick={() => navigate("/login", { state: location.state })}
                >
                  Back to sign-in options
                </Button>
              </div>
            </form>
          </>
        ) : (
          <>
            <h1 className="mb-1 text-lg font-semibold">Check your email</h1>
            <p className="text-ink-muted mb-4 text-sm">
              If an account exists for <strong>{challenge.email}</strong>, we
              emailed it a 6-digit sign-in code. Enter it here.
            </p>
            <div className="space-y-3">
              <CodeInput
                key={attempt}
                disabled={pending}
                error={error != null}
                onComplete={(code) => void onCodeComplete(code)}
              />
              <ErrorBanner error={error} message={codeErrorMessage} />
              <div className="text-center">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-ink-muted hover:text-ink min-h-0! py-1"
                  onClick={startOver}
                  disabled={pending}
                >
                  Start over
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>
    </AuthShell>
  );
}
