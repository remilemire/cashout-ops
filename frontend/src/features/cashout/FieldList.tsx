import { displayValue } from "@/lib/format";

import { groupFields } from "./fields";

/** Read-only key/value rendering of an extracted or verified data object. */
export function FieldList({
  data,
  schemaName,
}: {
  data: Record<string, unknown>;
  schemaName?: string | null;
}) {
  const groups = groupFields(schemaName, data);
  if (groups.length === 0) {
    return <p className="text-ink-muted text-sm">No extracted fields.</p>;
  }
  // Show headings only when there are multiple groups to distinguish.
  const showHeadings = groups.length > 1;
  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div key={group.heading ?? "other"}>
          {showHeadings && group.heading != null && (
            <p className="text-ink-muted mb-1.5 text-xs font-semibold tracking-wider uppercase">
              {group.heading}
            </p>
          )}
          <dl className="divide-line divide-y">
            {group.fields.map(({ key, label }) => (
              <div
                key={key}
                className="flex items-baseline justify-between gap-4 py-1.5 text-sm first:pt-0 last:pb-0"
              >
                <dt className="text-ink-muted">{label}</dt>
                <dd className="text-right font-medium break-all tabular-nums">
                  {displayValue(data[key]) || "—"}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
