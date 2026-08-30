// frontend/src/features/cashout/NewCashoutPage.tsx

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import type { ManualDocumentInput } from "@/api/types";
import { PageHeader } from "@/components/ui";
import { cx } from "@/lib/cx";
import { formatDateTime, localISODate } from "@/lib/format";

import { ManualDocumentDialog } from "./ManualDocumentDialog";
import { UploadZone } from "./UploadZone";
import { SubmissionStatusBadge } from "./status";

/** Local YYYY-MM-DD for the day before `isoDate` (DST-safe via setDate). */
function dayBefore(isoDate: string): string {
  const [year = 0, month = 1, day = 1] = isoDate.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  date.setDate(date.getDate() - 1);
  return localISODate(date);
}

export function NewCashoutPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [startedAt] = useState(() => new Date().toISOString());
  const [manualOpen, setManualOpen] = useState(false);
  // The day the cashout is for, as a local YYYY-MM-DD string. Yesterday
  // covers the after-midnight close-out and the missed-day catch-up.
  const [today] = useState(() => localISODate());
  const [businessDate, setBusinessDate] = useState(today);

  // The submission is created lazily with the first document, so an abandoned
  // page leaves nothing behind; a failed first upload reuses the created id.
  const ensureSubmissionId = async (): Promise<string> => {
    if (submissionId !== null) return submissionId;
    const submission = await cashoutApi.createSubmission({ businessDate });
    setSubmissionId(submission.id);
    void queryClient.invalidateQueries({
      queryKey: cashoutKeys.submissions,
    });
    return submission.id;
  };

  const initialUpload = useMutation({
    mutationFn: async (file: File) => {
      const targetSubmissionId = await ensureSubmissionId();
      const analysis = await cashoutApi.uploadDocument(
        targetSubmissionId,
        file,
      );
      return { analysis, submissionId: targetSubmissionId };
    },
    onSuccess: ({ analysis, submissionId: createdSubmissionId }) => {
      queryClient.setQueryData(cashoutKeys.analysis(analysis.id), analysis);
      navigate(`/cashouts/${createdSubmissionId}`, { replace: true });
    },
  });

  const manualUpload = useMutation({
    mutationFn: async ({
      file,
      input,
    }: {
      file: File;
      input: ManualDocumentInput;
    }) => {
      const targetSubmissionId = await ensureSubmissionId();
      const analysis = await cashoutApi.uploadManualDocument(
        targetSubmissionId,
        file,
        input,
      );
      return { analysis, submissionId: targetSubmissionId };
    },
    onSuccess: ({ analysis, submissionId: createdSubmissionId }) => {
      queryClient.setQueryData(cashoutKeys.analysis(analysis.id), analysis);
      navigate(`/cashouts/${createdSubmissionId}`, { replace: true });
    },
  });

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <Link
        to="/cashouts"
        className="text-ink-muted hover:text-ink inline-flex items-center gap-1 text-sm transition-colors"
      >
        <ArrowLeft className="size-4" />
        My cashouts
      </Link>

      <PageHeader
        title={`Cashout — ${formatDateTime(startedAt)}`}
        action={
          <div className="flex items-center gap-2">
            <SubmissionStatusBadge status="processing" />
          </div>
        }
      />

      {/* The chosen day is fixed at creation, which the first upload
          triggers — once the submission exists the control locks. */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-ink-muted">Cashout for</span>
        {[
          { label: "Today", value: today },
          { label: "Yesterday", value: dayBefore(today) },
        ].map(({ label, value }) => (
          <button
            key={label}
            type="button"
            disabled={submissionId !== null}
            onClick={() => setBusinessDate(value)}
            aria-pressed={businessDate === value}
            className={cx(
              "cursor-pointer rounded-lg border px-3 py-1.5 transition-colors",
              businessDate === value
                ? "border-accent/40 bg-accent/10 font-medium"
                : "border-line bg-surface-2",
              submissionId !== null && "cursor-not-allowed opacity-60",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <UploadZone
        onFile={(file) => initialUpload.mutate(file)}
        pending={initialUpload.isPending}
        error={initialUpload.error}
        onManualEntry={() => setManualOpen(true)}
      />

      <ManualDocumentDialog
        withFile
        open={manualOpen}
        onClose={() => setManualOpen(false)}
        pending={manualUpload.isPending}
        error={manualUpload.error}
        onSubmit={(input, file) => {
          if (file) manualUpload.mutate({ file, input });
        }}
      />
    </div>
  );
}
