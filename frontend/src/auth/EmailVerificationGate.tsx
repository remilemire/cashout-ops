// frontend/src/auth/EmailVerificationGate.tsx

import { MailCheck } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { User } from "@/api/types";
import { Dialog } from "@/components/dialog";
import { Button, TextField } from "@/components/ui";

import { useAuth } from "./useAuth";

/**
 * TODO(email-verification): the backend will add email verification. Once
 * `User` gains a verified flag, flip this predicate to it — the blocking
 * dialog below is already built and wired to this gate.
 */
function needsVerification(_user: User): boolean {
  void _user;
  return false;
}

export function EmailVerificationGate({
  user,
  children,
}: {
  user: User;
  children: ReactNode;
}) {
  if (!needsVerification(user)) return children;
  return (
    <>
      {children}
      <VerifyEmailDialog user={user} />
    </>
  );
}

/** Blocking modal shown to unverified accounts; not dismissible. */
function VerifyEmailDialog({ user }: { user: User }) {
  const { logout } = useAuth();
  const [code, setCode] = useState("");

  // TODO(email-verification): wire to the backend verify/resend endpoints
  // when they exist; on success invalidate the ["me"] query so the gate lifts.
  const submit = () => undefined;
  const resend = () => undefined;

  return (
    <Dialog open dismissible={false} title="Verify your email">
      <div className="space-y-3">
        <p className="text-ink-muted flex items-start gap-2 text-sm">
          <MailCheck className="text-accent-strong mt-0.5 size-4 shrink-0" />
          We sent a verification code to <strong>{user.email}</strong>. Enter it
          below to continue.
        </p>
        <TextField
          label="Verification code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
        <Button
          className="w-full"
          onClick={submit}
          disabled={code.length === 0}
        >
          Verify
        </Button>
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={resend}>
            Resend code
          </Button>
          <Button variant="ghost" size="sm" onClick={() => void logout()}>
            Log out
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
