import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import { isNotFound } from "@/api/client";
import type { CashoutDocumentAnalysis, FieldIssue } from "@/api/types";
import { Button, ConfidenceMeter, ErrorBanner } from "@/components/ui";
import { cx } from "@/lib/cx";
import { buildVerifiedData, displayValue } from "@/lib/format";

import { FieldList } from "./FieldList";
import { fieldLabelFor, groupFields } from "./fields";

/** Unverify preserves the corrections server-side; re-seed the edit state
 * from them so a re-edit starts from the corrected values, not the raw
 * extraction. */
function seedEdits(analysis: CashoutDocumentAnalysis): Record<string, string> {
  const verified = analysis.verifiedDataJson;
  if (verified == null) return {};
  const extracted = analysis.extractedDataJson ?? {};
  const edits: Record<string, string> = {};
  for (const key of Object.keys(extracted)) {
    const corrected = displayValue(verified[key]);
    if (corrected !== displayValue(extracted[key])) edits[key] = corrected;
  }
  return edits;
}

/**
 * The cashier's review step: extracted fields (editable), the issues the AI
 * flagged inline on the fields they concern, and both confidences. Verify
 * sends corrections only when something was actually changed.
 */
export function VerificationForm({
  analysis,
  submissionId,
  editable,
  secondaryAction,
}: {
  analysis: CashoutDocumentAnalysis;
  submissionId: string;
  editable: boolean;
  /** Sits beside Verify in the action row; only shown while editable. */
  secondaryAction?: ReactNode;
}) {
  const queryClient = useQueryClient();
  const [edits, setEdits] = useState<Record<string, string>>(() =>
    seedEdits(analysis),
  );
  const extracted = analysis.extractedDataJson ?? {};
  const issues = analysis.issues ?? [];

  const issuesFor = (key: string): FieldIssue[] =>
    issues.filter(
      (issue) => issue.path === key || issue.path.startsWith(`${key}.`),
    );
  const generalIssues = issues.filter(
    (issue) =>
      !Object.keys(extracted).some((key) => issuesFor(key).includes(issue)),
  );

  const groups = groupFields(analysis.schemaName, extracted);
  // Show headings only when there are multiple groups to distinguish.
  const showHeadings = groups.length > 1;

  const verifiedData = buildVerifiedData(extracted, edits);
  const changedCount = verifiedData
    ? Object.keys(edits).filter(
        (key) => edits[key] !== displayValue(extracted[key]),
      ).length
    : 0;

  const verify = useMutation({
    mutationFn: () =>
      cashoutApi.verifyAnalysis(
        analysis.id,
        verifiedData ? { verifiedData } : {},
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(cashoutKeys.analysis(updated.id), updated);
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
    // The analysis (or its upload or submission) was deleted elsewhere:
    // refresh the detail so the dead form disappears instead of failing.
    onError: (error) => {
      if (isNotFound(error)) {
        void queryClient.invalidateQueries({
          queryKey: cashoutKeys.submission(submissionId),
        });
      }
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-4">
        <ConfidenceMeter
          label="Classification confidence"
          value={analysis.classificationConfidence}
        />
        <ConfidenceMeter
          label="Extraction confidence"
          value={analysis.extractionConfidence}
        />
      </div>

      {generalIssues.length > 0 && (
        <div className="border-warning/40 bg-warning/10 rounded-lg border px-3 py-2 text-sm">
          <p className="flex items-center gap-1.5 font-medium">
            <AlertTriangle className="text-warning size-4" />
            The AI flagged possible problems
          </p>
          <ul className="text-ink-muted mt-1 ml-5 list-disc">
            {generalIssues.map((issue, index) => (
              <li key={index}>
                <strong>
                  {fieldLabelFor(analysis.schemaName, issue.path)}
                </strong>
                : {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {editable ? (
        <>
          <div className="space-y-5">
            {groups.map((group) => (
              <div key={group.heading ?? "other"} className="space-y-2.5">
                {showHeadings && group.heading != null && (
                  <p className="text-ink-muted text-xs font-semibold tracking-wider uppercase">
                    {group.heading}
                  </p>
                )}
                {group.fields.map(({ key, label }) => {
                  const value = extracted[key];
                  const fieldIssues = issuesFor(key);
                  const edited =
                    key in edits && edits[key] !== displayValue(value);
                  return (
                    <label key={key} className="block">
                      <span className="mb-1 flex items-center gap-2 text-sm font-medium">
                        {label}
                        {edited && (
                          <span className="text-accent-strong text-xs font-normal">
                            edited
                          </span>
                        )}
                      </span>
                      <input
                        aria-label={label}
                        className={cx(
                          "bg-surface min-h-11 w-full rounded-lg border px-3 text-sm",
                          "focus:ring-accent/50 outline-none focus:ring-2",
                          fieldIssues.length > 0 && !edited
                            ? "border-warning"
                            : "border-line",
                        )}
                        value={edits[key] ?? displayValue(value)}
                        onChange={(event) =>
                          setEdits((prev) => ({
                            ...prev,
                            [key]: event.target.value,
                          }))
                        }
                      />
                      {edited && (
                        <span className="text-ink-muted mt-1 block text-xs break-all">
                          Original: {displayValue(value) || "—"}
                        </span>
                      )}
                      {fieldIssues.map((issue, index) => (
                        <span
                          key={index}
                          className="text-warning mt-1 flex items-center gap-1 text-xs"
                        >
                          <AlertTriangle className="size-3" />
                          {issue.message}
                        </span>
                      ))}
                    </label>
                  );
                })}
              </div>
            ))}
          </div>

          <ErrorBanner error={verify.error} />
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button onClick={() => verify.mutate()} loading={verify.isPending}>
              <Check className="size-4" />
              {changedCount > 0
                ? `Verify with ${changedCount} correction${changedCount > 1 ? "s" : ""}`
                : "Looks right — verify"}
            </Button>
            {secondaryAction}
          </div>
        </>
      ) : (
        <FieldList data={extracted} schemaName={analysis.schemaName} />
      )}
    </div>
  );
}
