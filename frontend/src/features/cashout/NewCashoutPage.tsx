// frontend/src/features/cashout/NewCashoutPage.tsx

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import type { ManualDocumentInput } from "@/api/types";
import { PageHeader, TextField } from "@/components/ui";
import { formatDateTime, localISODate } from "@/lib/format";

import { ManualDocumentDialog } from "./ManualDocumentDialog";
import { UploadZone } from "./UploadZone";
import { SubmissionStatusBadge } from "./status";

export function NewCashoutPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [startedAt] = useState(() => new Date().toISOString());
  const [manualOpen, setManualOpen] = useState(false);
  // The day the cashout is for, as a local YYYY-MM-DD string. Defaults to
  // today; an after-midnight close-out or a missed-day catch-up picks the
  // actual day.
  const [today] = useState(() => localISODate());
  const [businessDate, setBusinessDate] = useState(today);

  // The submission is created lazily with the first document, so an abandoned
  // page leaves nothing behind; a failed first upload reuses the created id.
  const ensureSubmissionId = async (): Promise<string> => {
    if (submissionId !== null) return submissionId;
    const submission = await cashoutApi.createSubmission({
      // A cleared date input falls back to today.
      businessDate: businessDate || today,
    });
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
      <div className="w-44">
        <TextField
          label="Cashout for"
          type="date"
          value={businessDate}
          disabled={submissionId !== null}
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
