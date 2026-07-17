// frontend/src/components/ui.tsx

/** Small shared primitives. Colors come exclusively from the theme tokens. */

import { AlertCircle, Inbox } from "lucide-react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
} from "react";

import { ApiError } from "@/api/client";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// ---------- Button ----------

type ButtonVariant = "primary" | "outline" | "ghost" | "danger";
type ButtonSize = "md" | "sm";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-on-accent hover:bg-accent-strong border border-transparent shadow-sm",
  outline: "border border-line bg-surface hover:bg-surface-2",
  ghost: "border border-transparent hover:bg-surface-2",
  danger: "bg-danger/10 text-danger border border-danger/30 hover:bg-danger/20",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  md: "min-h-11 px-4 text-sm",
  sm: "min-h-9 px-3 text-xs",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium",
        "transition-colors disabled:pointer-events-none disabled:opacity-50",
        BUTTON_SIZES[size],
        BUTTON_VARIANTS[variant],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  );
}

// ---------- Surfaces ----------

export function Card({
  className,
  children,
  padded = true,
}: {
  className?: string;
  children: ReactNode;
  padded?: boolean;
}) {
  return (
    <div
      className={cx(
        "border-line bg-surface rounded-xl border shadow-xs",
        padded && "p-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <h1 className="truncate text-xl font-semibold tracking-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="text-ink-muted mt-0.5 text-sm">{subtitle}</p>
        )}
      </div>
      {action}
    </div>
  );
}

// ---------- Status ----------

type BadgeTone =
  | "neutral"
  | "accent"
  | "success"
  | "warning"
  | "danger"
  | "info";

const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-ink-muted",
  accent: "bg-accent/15 text-accent-strong",
  success: "bg-success/15 text-success",
  warning: "bg-warning/20 text-warning",
  danger: "bg-danger/15 text-danger",
  info: "bg-info/15 text-info",
};

export function Badge({
  tone = "neutral",
  icon,
  children,
}: {
  tone?: BadgeTone;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        BADGE_TONES[tone],
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/** Horizontal 0–1 meter; tone follows the value (high = good). */
export function ConfidenceMeter({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  const percent = value == null ? 0 : Math.round(value * 100);
  const tone =
    value == null
      ? "bg-line"
      : value >= 0.8
        ? "bg-success"
        : value >= 0.5
          ? "bg-warning"
          : "bg-danger";
  return (
    <div className="min-w-0 flex-1">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-ink-muted truncate text-xs">{label}</span>
        <span className="text-xs font-semibold tabular-nums">
          {value == null ? "—" : `${percent}%`}
        </span>
      </div>
      <div className="bg-surface-2 h-1.5 overflow-hidden rounded-full">
        <div
          className={cx("h-full rounded-full transition-all", tone)}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

// ---------- Feedback ----------

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cx(
        "border-line border-t-accent inline-block animate-spin rounded-full border-2",
        className ?? "size-5",
      )}
    />
  );
}

export function FullScreenSpinner() {
  return (
    <div className="flex min-h-dvh items-center justify-center">
      <Spinner className="size-8" />
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cx("bg-surface-2 animate-pulse rounded-lg", className)}
    />
  );
}

/** A stack of card-shaped skeletons for list/table loading states. */
export function SkeletonList({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }, (_, index) => (
        <Skeleton key={index} className="h-16" />
      ))}
    </div>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message =
    error instanceof ApiError
      ? error.message
      : "Something went wrong. Please try again.";
  return (
    <div className="border-danger/30 bg-danger/10 text-danger flex items-start gap-2 rounded-lg border px-3 py-2 text-sm">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      {message}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  icon,
  action,
}: {
  title: string;
  hint?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="border-line rounded-xl border border-dashed px-4 py-12 text-center">
      <div className="text-ink-muted mx-auto mb-3 w-fit">
        {icon ?? <Inbox className="size-8" strokeWidth={1.5} />}
      </div>
      <p className="font-medium">{title}</p>
      {hint && <p className="text-ink-muted mt-1 text-sm">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

// ---------- Forms ----------

export function TextField({
  label,
  error,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium">{label}</span>
      <input
        className={cx(
          "bg-surface min-h-11 w-full rounded-lg border px-3 text-sm",
          "focus:ring-accent/50 outline-none focus:ring-2",
          error ? "border-danger" : "border-line",
          className,
        )}
        {...rest}
      />
      {error && <span className="text-danger mt-1 block text-xs">{error}</span>}
    </label>
  );
}
