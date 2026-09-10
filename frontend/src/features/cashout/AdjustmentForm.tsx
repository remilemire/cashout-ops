import { ApiError } from "@/api/client";
import type { JsonValue } from "@/api/types";
import { Badge, TextField } from "@/components/ui";

/** What an admin can adjust the cross-check with; a deposit is the only kind so far. */
export type AdjustmentKind = "deposit";

const KIND_OPTIONS: { value: AdjustmentKind; label: string }[] = [
  { value: "deposit", label: "Deposit" },
];

/** The form's values; `kind` null means no adjustment, and nothing is sent. */
export interface AdjustmentValues {
  kind: AdjustmentKind | null;
  depositTotal: string;
  note: string;
}

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
 * An admin's adjustment, offered once completing fails the card payment
 * cross-check: a single select at first, and the chosen kind's fields once
 * one is picked. Presentational; the caller owns the values and folds them
 * into the completion request.
 */
export function AdjustmentForm({
  values,
  onChange,
  error,
}: {
  values: AdjustmentValues;
  onChange: (next: AdjustmentValues) => void;
  error: unknown;
}) {
  const hint = gapHint(error);
  const fieldError = (field: string): string | undefined =>
    error instanceof ApiError ? error.messageFor(field) : undefined;

  return (
    <div className="space-y-2">
      <label className="block">
        <span className="mb-1 flex items-center gap-2 text-sm font-medium">
          Adjustment
          <Badge tone="accent">Admin</Badge>
        </span>
        <select
          className="bg-surface border-line focus:ring-accent/50 h-11 w-full rounded-lg border px-3 text-sm outline-none focus:ring-2 sm:w-64"
          value={values.kind ?? ""}
          onChange={(event) => {
            const kind =
              KIND_OPTIONS.find((option) => option.value === event.target.value)
                ?.value ?? null;
            // Picking "None" withdraws the adjustment, values and all.
            onChange(
              kind == null
                ? { kind: null, depositTotal: "", note: "" }
                : { ...values, kind },
            );
          }}
        >
          <option value="">None</option>
          {KIND_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      {values.kind === "deposit" && (
        <>
          <p className="text-ink-muted text-xs">
            A deposit the TouchBistro report counts among its card payments but
            no terminal summary shows. It is subtracted from the card payments
            before the cross-check.
          </p>
          {hint != null && <p className="text-xs">{hint}</p>}
          <TextField
            label="Deposit amount"
            inputMode="decimal"
            value={values.depositTotal}
            error={fieldError("depositTotal")}
            onChange={(event) =>
              onChange({ ...values, depositTotal: event.target.value })
            }
          />
          <TextField
            label="Note (optional)"
            value={values.note}
            error={fieldError("note")}
            onChange={(event) =>
              onChange({ ...values, note: event.target.value })
            }
          />
        </>
      )}
    </div>
  );
}
