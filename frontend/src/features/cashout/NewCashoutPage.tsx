// frontend/src/features/cashout/NewCashoutPage.tsx

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import type { CashoutSubmission, ManualDocumentInput } from "@/api/types";
import { PageHeader, TextField } from "@/components/ui";
import { formatDateTime, localISODate } from "@/lib/format";

import { ManualDocumentDialog } from "./ManualDocumentDialog";
import { UploadZone } from "./UploadZone";
import { SubmissionStatusBadge } from "./status";

export function NewCashoutPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submission, setSubmission] = useState<CashoutSubmission | null>(null);
  const [startedAt] = useState(() => new Date().toISOString());
  const [manualOpen, setManualOpen] = useState(false);
  // The day the cashout is for, as a local YYYY-MM-DD string. Defaults to
  // today; an after-midnight close-out or a missed-day catch-up picks the
  // actual day.
  const [today] = useState(() => localISODate());
  const [businessDate, setBusinessDate] = useState(today);

  // The submission is created lazily with the first document, so an abandoned
  // page leaves nothing behind. A failed first upload reuses the created one,
  // re-dated first if the day was changed in the meantime.
  const ensureSubmissionId = async (): Promise<string> => {
    // A cleared date input falls back to today.
    const targetDate = businessDate || today;
    if (submission !== null && submission.businessDate === targetDate) {
      return submission.id;
    }
    const saved =
      submission === null
        ? await cashoutApi.createSubmission({ businessDate: targetDate })
        : await cashoutApi.updateSubmission(submission.id, {
            businessDate: targetDate,
          });
    setSubmission(saved);
    // The cashier's list shows each cashout's day.
    void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
    return saved.id;
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

      <div className="w-44">
        <TextField
          label="Cashout for"
          type="date"
          value={businessDate}
          onChange={(event) => setBusinessDate(event.target.value)}
        />
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
