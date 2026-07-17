// frontend/src/features/cashout/FieldList.tsx

import { displayValue, fieldLabel } from "@/lib/format";

/** Read-only key/value rendering of an extracted or verified data object. */
export function FieldList({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <p className="text-ink-muted text-sm">No extracted fields.</p>;
  }
  return (
    <dl className="divide-line divide-y">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="flex items-baseline justify-between gap-4 py-1.5 text-sm first:pt-0 last:pb-0"
        >
          <dt className="text-ink-muted">{fieldLabel(key)}</dt>
          <dd className="text-right font-medium break-all tabular-nums">
            {displayValue(value) || "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}
