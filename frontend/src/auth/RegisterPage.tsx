// frontend/src/auth/RegisterPage.tsx

import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button, Card, ErrorBanner, TextField } from "@/components/ui";

import { useAuth } from "./AuthProvider";
import { AuthShell } from "./LoginPage";

export function RegisterPage() {
  const { user, isLoading, register } = useAuth();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (!isLoading && user) return <Navigate to="/" replace />;

  const fieldError = (field: string) =>
    error instanceof ApiError ? error.detailFor(field) : undefined;

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      await register({
        email: String(form.get("email")),
        firstName: String(form.get("firstName")),
        lastName: String(form.get("lastName")),
        password: String(form.get("password")),
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
          <div className="grid grid-cols-2 gap-3">
            <TextField
              label="First name"
              name="firstName"
              autoComplete="given-name"
              required
              error={fieldError("firstName")}
            />
            <TextField
              label="Last name"
              name="lastName"
              autoComplete="family-name"
              required
              error={fieldError("lastName")}
            />
          </div>
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
