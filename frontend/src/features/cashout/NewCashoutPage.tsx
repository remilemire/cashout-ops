import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import { PageHeader } from "@/components/ui";
import { formatDateTime } from "@/lib/format";

import { UploadZone } from "./UploadZone";
import { SubmissionStatusBadge } from "./status";

export function NewCashoutPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [startedAt] = useState(() => new Date().toISOString());

  const initialUpload = useMutation({
    mutationFn: async (file: File) => {
      let targetSubmissionId = submissionId;

      if (targetSubmissionId === null) {
        const submission = await cashoutApi.createSubmission();
        targetSubmissionId = submission.id;
        setSubmissionId(targetSubmissionId);
        void queryClient.invalidateQueries({
          queryKey: cashoutKeys.submissions,
        });
      }

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
            <SubmissionStatusBadge status="PROCESSING" />
          </div>
        }
      />

      <UploadZone
        onFile={(file) => initialUpload.mutate(file)}
        pending={initialUpload.isPending}
        error={initialUpload.error}
      />
    </div>
  );
}
