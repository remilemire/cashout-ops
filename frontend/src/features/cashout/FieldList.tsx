import { displayValue } from "@/lib/format";

import { groupFields } from "./fields";

/** Read-only key/value rendering of an extracted or verified data object. */
export function FieldList({
  data,
  schemaName,
  originalData,
}: {
  data: Record<string, unknown>;
  schemaName?: string | null;
  /** When provided, show corrections beside their original extracted values. */
  originalData?: Record<string, unknown>;
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
                  {originalData &&
                  displayValue(originalData[key]) !==
                    displayValue(data[key]) ? (
                    <>
                      <span className="text-ink-muted font-normal">
                        <span className="sr-only">Original: </span>
                        {displayValue(originalData[key]) || "—"}
                      </span>{" "}
                      <span aria-hidden="true">→</span>{" "}
                      <strong className="text-accent-strong font-bold">
                        <span className="sr-only">Corrected: </span>
                        {displayValue(data[key]) || "—"}
                      </strong>
                    </>
                  ) : (
                    displayValue(data[key]) || "—"
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
