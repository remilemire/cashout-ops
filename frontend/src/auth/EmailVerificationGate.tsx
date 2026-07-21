// frontend/src/auth/EmailVerificationGate.tsx

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import {
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
  type ReactNode,
  type SyntheticEvent,
} from "react";

import { emailVerificationApi } from "@/api/emailVerification";
import type { User } from "@/api/types";
import { Dialog } from "@/components/dialog";
import { Button, ErrorBanner } from "@/components/ui";
import { cx } from "@/lib/cx";

import { useAuth } from "./useAuth";

const ME_KEY = ["me"] as const;

/** Number of digits in a verification code (mirrors the backend). */
const CODE_LENGTH = 6;

const EMPTY_CODE = Array.from({ length: CODE_LENGTH }, () => "");

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
  const [digits, setDigits] = useState<string[]>(EMPTY_CODE);
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);

  const focusInput = (index: number) => {
    const input = inputsRef.current[index];
    input?.focus();
    input?.select();
  };

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
    onSuccess: () => {
      // The previous code is now invalidated server-side; clear the boxes so
      // the user starts fresh with the new one.
      verify.reset();
      setDigits(EMPTY_CODE);
      focusInput(0);
    },
  });

  /** Submit once a full code is present; the source of the code varies
   * (last digit typed, a paste, or the Verify button). */
  const submit = (code: string) => {
    if (code.length === CODE_LENGTH && !verify.isPending) {
      verify.mutate({ code });
    }
  };

  const commit = (next: string[], focusIndex: number) => {
    setDigits(next);
    focusInput(focusIndex);
    if (next.every(Boolean)) submit(next.join(""));
  };

  /** Write `raw`'s digits into the boxes starting at `start`, ignoring
   * non-digits. Used for both single keystrokes and multi-digit pastes. */
  const fillFrom = (start: number, raw: string) => {
    const chars = raw.replace(/\D/g, "");
    const next = [...digits];
    let cursor = start;
    for (const char of chars) {
      if (cursor >= CODE_LENGTH) break;
      next[cursor] = char;
      cursor += 1;
    }
    commit(next, Math.min(cursor, CODE_LENGTH - 1));
  };

  const onDigitChange = (index: number, raw: string) => {
    const cleaned = raw.replace(/\D/g, "");
    if (cleaned.length > 1) {
      // Autofill / one-time-code can drop the whole code into a single box.
      fillFrom(index, cleaned);
      return;
    }
    const next = [...digits];
    next[index] = cleaned;
    commit(next, cleaned ? Math.min(index + 1, CODE_LENGTH - 1) : index);
  };

  const onDigitKeyDown = (
    index: number,
    event: KeyboardEvent<HTMLInputElement>,
  ) => {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      // Nothing to delete here: step back and clear the previous box.
      event.preventDefault();
      const next = [...digits];
      next[index - 1] = "";
      setDigits(next);
      focusInput(index - 1);
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      focusInput(index - 1);
    } else if (event.key === "ArrowRight" && index < CODE_LENGTH - 1) {
      event.preventDefault();
      focusInput(index + 1);
    }
  };

  const onDigitPaste = (
    index: number,
    event: ClipboardEvent<HTMLInputElement>,
  ) => {
    event.preventDefault();
    fillFrom(index, event.clipboardData.getData("text"));
  };

  const onSubmit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    submit(digits.join(""));
  };

  const complete = digits.every(Boolean);

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
        <div>
          <span className="mb-1 block text-sm font-medium">
            Verification code
          </span>
          <div
            role="group"
            aria-label="Verification code"
            className="flex justify-between gap-2"
          >
            {digits.map((digit, index) => (
              <input
                key={index}
                ref={(element) => {
                  inputsRef.current[index] = element;
                }}
                type="text"
                inputMode="numeric"
                autoComplete={index === 0 ? "one-time-code" : "off"}
                pattern="[0-9]*"
                maxLength={1}
                aria-label={`Digit ${index + 1}`}
                value={digit}
                onChange={(event) => onDigitChange(index, event.target.value)}
                onKeyDown={(event) => onDigitKeyDown(index, event)}
                onPaste={(event) => onDigitPaste(index, event)}
                onFocus={(event) => event.currentTarget.select()}
                className={cx(
                  "bg-surface size-11 min-w-0 flex-1 rounded-lg border text-center text-lg font-semibold",
                  "focus:ring-accent/50 outline-none focus:ring-2",
                  verify.isError ? "border-danger" : "border-line",
                )}
              />
            ))}
          </div>
        </div>

        <ErrorBanner error={verify.error} />
        <ErrorBanner error={resend.error} />
        {resend.isSuccess && (
          <p className="text-success text-sm">A new code is on its way.</p>
        )}

        <Button
          type="submit"
          className="w-full"
          loading={verify.isPending}
          disabled={!complete}
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
