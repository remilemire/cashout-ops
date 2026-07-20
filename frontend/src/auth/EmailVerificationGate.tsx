// frontend/src/auth/EmailVerificationGate.tsx

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import { useState, type ReactNode, type SyntheticEvent } from "react";

import { emailVerificationApi } from "@/api/emailVerification";
import type { User } from "@/api/types";
import { Dialog } from "@/components/dialog";
import { Button, ErrorBanner, TextField } from "@/components/ui";

import { useAuth } from "./useAuth";

const ME_KEY = ["me"] as const;

/** Accounts are gated until they confirm the code emailed at registration. */
function needsVerification(user: User): boolean {
  return user.emailVerifiedAt === null;
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
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");

  const verify = useMutation({
    mutationFn: emailVerificationApi.verify,
    onSuccess: async (verified) => {
      // Seed ["me"] so the gate lifts, then refetch everything else: the
      // guarded queries rendered behind the dialog failed with
      // EMAIL_NOT_VERIFIED and need to reload now that we're verified.
      queryClient.setQueryData(ME_KEY, verified);
      await queryClient.invalidateQueries();
    },
  });

  const resend = useMutation({
    mutationFn: emailVerificationApi.resend,
    onSuccess: () => verify.reset(),
  });

  const onSubmit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = code.trim();
    if (trimmed) verify.mutate({ code: trimmed });
  };

  return (
    <Dialog open dismissible={false} title="Verify your email">
      <form onSubmit={onSubmit} className="space-y-3">
        <p className="text-ink-muted flex items-start gap-2 text-sm">
          <MailCheck className="text-accent-strong mt-0.5 size-4 shrink-0" />
          <span>
            We sent a verification code to <strong>{user.email}</strong>. Enter
            it below to continue.
          </span>
        </p>
        <TextField
          label="Verification code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />

        <ErrorBanner error={verify.error} />
        <ErrorBanner error={resend.error} />
        {resend.isSuccess && (
          <p className="text-success text-sm">A new code is on its way.</p>
        )}

        <Button
          type="submit"
          className="w-full"
          loading={verify.isPending}
          disabled={code.trim().length === 0}
        >
          Verify
        </Button>
        <div className="flex items-center justify-between">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            loading={resend.isPending}
            onClick={() => resend.mutate()}
          >
            Resend code
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void logout()}
          >
            Log out
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
