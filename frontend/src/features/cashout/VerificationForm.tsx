// frontend/src/features/cashout/VerificationForm.tsx

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import type { CashoutDocumentAnalysis, FieldIssue } from "@/api/types";
import { Button, ConfidenceMeter, ErrorBanner } from "@/components/ui";
import { cx } from "@/lib/cx";
import { buildVerifiedData, displayValue, fieldLabel } from "@/lib/format";

import { FieldList } from "./FieldList";

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
  const [edits, setEdits] = useState<Record<string, string>>({});
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
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-4">
        <ConfidenceMeter
          label="Classification"
          value={analysis.classificationConfidence}
        />
        <ConfidenceMeter
          label="Extraction"
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
                <strong>{fieldLabel(issue.path)}</strong>: {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {editable ? (
        <>
          <div className="space-y-2.5">
            {Object.entries(extracted).map(([key, value]) => {
              const fieldIssues = issuesFor(key);
              const edited = key in edits && edits[key] !== displayValue(value);
              return (
                <label key={key} className="block">
                  <span className="mb-1 flex items-center gap-2 text-sm font-medium">
                    {fieldLabel(key)}
                    {edited && (
                      <span className="text-accent-strong text-xs font-normal">
                        edited
                      </span>
                    )}
                  </span>
                  <input
                    aria-label={fieldLabel(key)}
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
        <FieldList data={extracted} />
      )}
    </div>
  );
}
