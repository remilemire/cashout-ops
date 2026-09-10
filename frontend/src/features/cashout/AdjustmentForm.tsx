// frontend/src/features/cashout/AdjustmentForm.tsx

import { ApiError } from "@/api/client";
import type { JsonValue } from "@/api/types";
import { Badge, TextField } from "@/components/ui";

/** A decimal string as integer cents, so the gap arithmetic stays exact. */
function cents(value: JsonValue | undefined): number | undefined {
  if (typeof value !== "string") return undefined;
  const amount = Math.round(Number(value) * 100);
  return Number.isFinite(amount) ? amount : undefined;
}

function dollars(amount: number): string {
  return `$${(amount / 100).toFixed(2)}`;
}

/**
 * How far the refused cross-check was off, from the totals the mismatch
 * error carries — net of any deposit that attempt already applied. Nothing
 * for another error, or an older backend that sends no totals.
 */
function gapHint(error: unknown): string | undefined {
  if (
    !(error instanceof ApiError) ||
    error.code !== "RECONCILE_CARD_PAYMENT_MISMATCH"
  ) {
    return undefined;
  }
  const cardPayments = cents(error.ctx.cardPaymentTotal);
  const grandTotals = cents(error.ctx.serverSummaryTotal);
  if (cardPayments === undefined || grandTotals === undefined) return undefined;
  const gap = cardPayments - (cents(error.ctx.depositTotal) ?? 0) - grandTotals;
  if (gap > 0) {
    return `The report's card payments exceed the summaries by ${dollars(gap)}.`;
  }
  if (gap < 0) {
    return `The summaries exceed the report's card payments by ${dollars(-gap)} — a deposit cannot close that.`;
  }
  return undefined;
}

/**
 * An admin's deposit adjustment, offered once completing fails the card
 * payment cross-check. Presentational; the caller owns the values and folds
 * them into the completion request.
 */
export function AdjustmentForm({
  depositTotal,
  note,
  onChange,
  error,
}: {
  depositTotal: string;
  note: string;
  onChange: (next: { depositTotal: string; note: string }) => void;
  error: unknown;
}) {
  const hint = gapHint(error);
  const fieldError = (field: string): string | undefined =>
    error instanceof ApiError ? error.messageFor(field) : undefined;

  return (
    <div className="border-line space-y-2 rounded-lg border p-3">
      <p className="flex items-center gap-2 text-sm font-medium">
        Record a deposit
        <Badge tone="accent">Admin</Badge>
      </p>
      <p className="text-ink-muted text-xs">
        A deposit the TouchBistro report counts among its card payments but no
        terminal summary shows. It is subtracted from the card payments before
        the cross-check.
      </p>
      {hint != null && <p className="text-xs">{hint}</p>}
      <TextField
        label="Deposit amount"
        inputMode="decimal"
        value={depositTotal}
        error={fieldError("depositTotal")}
        onChange={(event) =>
          onChange({ depositTotal: event.target.value, note })
        }
      />
      <TextField
        label="Note (optional)"
        value={note}
        error={fieldError("note")}
        onChange={(event) =>
          onChange({ depositTotal, note: event.target.value })
        }
      />
    </div>
  );
}
