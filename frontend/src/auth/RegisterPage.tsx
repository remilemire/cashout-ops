// frontend/src/auth/RegisterPage.tsx

import { useState, type SyntheticEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button, Card, ErrorBanner, TextField } from "@/components/ui";

import { AuthShell } from "./LoginPage";
import { useAuth } from "./useAuth";

export function RegisterPage() {
  const { user, isLoading, register } = useAuth();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [confirmError, setConfirmError] = useState<string | undefined>(
    undefined,
  );

  if (!isLoading && user) return <Navigate to="/" replace />;

  const fieldError = (field: string) =>
    error instanceof ApiError ? error.messageFor(field) : undefined;

  const onSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    if (password !== String(form.get("confirmPassword"))) {
      setConfirmError("Passwords do not match.");
      return;
    }
    setConfirmError(undefined);
    setPending(true);
    setError(null);
    try {
      await register({
        email: String(form.get("email")),
        fullName: String(form.get("fullName")),
        password,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  };

  return (
    <AuthShell>
      <Card>
        <h1 className="mb-4 text-lg font-semibold">Create your account</h1>
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-3">
          <TextField
            label="Full name"
            name="fullName"
            autoComplete="name"
            required
            error={fieldError("fullName")}
          />
          <TextField
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            required
            error={fieldError("email")}
          />
          <TextField
            label="Password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            error={fieldError("password")}
          />
          <TextField
            label="Confirm password"
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            required
            error={confirmError}
          />
          <ErrorBanner error={error} />
          <Button type="submit" loading={pending} className="w-full">
            Register
          </Button>
        </form>
        <p className="text-ink-muted mt-4 text-center text-sm">
          Already have an account?{" "}
          <Link
            to="/login"
            className="text-accent-strong font-medium hover:underline"
          >
            Log in
          </Link>
        </p>
      </Card>
    </AuthShell>
  );
}
