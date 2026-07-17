// frontend/src/auth/LoginPage.tsx

import { GlassWater } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { Button, Card, ErrorBanner, TextField } from "@/components/ui";

import { useAuth } from "./AuthProvider";

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

export function LoginPage() {
  const { user, isLoading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (!isLoading && user) return <Navigate to="/" replace />;

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    // AGENT: FormEvent is deprecated
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      await login({
        email: String(form.get("email")),
        password: String(form.get("password")),
      });
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  };

  return (
    <AuthShell>
      <Card>
        <h1 className="mb-4 text-lg font-semibold">Log in</h1>
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-3">
          <TextField
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            required
          />
          <TextField
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
          <ErrorBanner error={error} />
          <Button type="submit" loading={pending} className="w-full">
            Log in
          </Button>
        </form>
        <p className="text-ink-muted mt-4 text-center text-sm">
          No account?{" "}
          <Link
            to="/register"
            className="text-accent-strong font-medium hover:underline"
          >
            Register
          </Link>
        </p>
      </Card>
    </AuthShell>
  );
}
