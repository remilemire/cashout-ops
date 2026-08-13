// frontend/src/features/cashout/SubmissionPage.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, PartyPopper, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import { useAuth } from "@/auth/useAuth";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  FullScreenSpinner,
  PageHeader,
} from "@/components/ui";
import { formatDateTime } from "@/lib/format";

import { DataCard } from "./DataCard";
import { DocumentCard } from "./DocumentCard";
import { UploadZone } from "./UploadZone";
import { SubmissionStatusBadge } from "./status";

export function SubmissionPage() {
  const { submissionId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [cancelOpen, setCancelOpen] = useState(false);

  const detailQuery = useQuery({
    queryKey: cashoutKeys.submission(submissionId),
    queryFn: () => cashoutApi.getSubmission(submissionId),
    enabled: submissionId !== "",
  });

  const upload = useMutation({
    mutationFn: (file: File) => cashoutApi.uploadDocument(submissionId, file),
    onSuccess: (analysis) => {
      queryClient.setQueryData(cashoutKeys.analysis(analysis.id), analysis);
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
  });

  const complete = useMutation({
    mutationFn: () => cashoutApi.completeSubmission(submissionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cashoutApi.cancelSubmission(submissionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
      navigate("/cashouts");
    },
  });

  const submission = detailQuery.data;
  if (detailQuery.isLoading) return <FullScreenSpinner />;
  if (!submission) return <ErrorBanner error={detailQuery.error} />;

  // Admins can view anyone's submission; only the owner can act on it.
  const isOwner = submission.submittedByUserId === user?.id;
  const isAdminView = !isOwner;
  const editable = isOwner && submission.status === "processing";
  // Cancel stays available for the owner until the cashout is completed.
  const canCancel = isOwner && submission.status !== "completed";
  const documents = submission.documents;
  const verifiedCount = documents.filter(
    (doc) => doc.analysis?.status === "verified",
  ).length;
  const allVerified =
    documents.length > 0 && verifiedCount === documents.length;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Link
          to={isAdminView ? "/admin/submissions" : "/cashouts"}
          className="text-ink-muted hover:text-ink inline-flex items-center gap-1 text-sm transition-colors"
        >
          <ArrowLeft className="size-4" />
          {isAdminView ? "All submissions" : "My cashouts"}
        </Link>
        {canCancel && (
          <Button
            variant="danger"
            size="sm"
            onClick={() => setCancelOpen(true)}
          >
            Cancel cashout
          </Button>
        )}
      </div>

      <PageHeader
        title={`Cashout — ${formatDateTime(submission.submittedAt)}`}
        subtitle={
          isAdminView
            ? `Submitted by ${submission.submittedBy.fullName} (${submission.submittedBy.email})`
            : undefined
        }
        action={
          <div className="flex items-center gap-2">
            {documents.length > 0 && submission.status === "processing" && (
              <Badge tone={allVerified ? "success" : "neutral"}>
                {verifiedCount}/{documents.length} verified
              </Badge>
            )}
            <SubmissionStatusBadge status={submission.status} />
          </div>
        }
      />

      {submission.status === "completed" && (
        <Card className="border-success/40 bg-success/10 flex items-center gap-3">
          <PartyPopper className="text-success size-6 shrink-0" />
          <div>
            <p className="font-medium">Cashout completed</p>
            <p className="text-ink-muted text-sm">
              The verified documents were reconciled into the data below.
            </p>
          </div>
        </Card>
      )}

      {submission.data && <DataCard data={submission.data} />}

      {documents.length === 0 && !editable && (
        <EmptyState title="No documents" />
      )}

      {documents.map((document) => (
        <DocumentCard
          key={document.id}
          document={document}
          submissionId={submission.id}
          editable={editable}
        />
      ))}

      {editable && (
        <UploadZone
          onFile={(file) => upload.mutate(file)}
          pending={upload.isPending}
          error={upload.error}
        />
      )}

      {editable && documents.length > 0 && (
        <CompletePrompt
          allVerified={allVerified}
          pending={complete.isPending}
          error={complete.error}
          onComplete={() => complete.mutate()}
        />
      )}

      <ConfirmDialog
        open={cancelOpen}
        onClose={() => setCancelOpen(false)}
        title="Cancel cashout?"
        confirmLabel="Cancel cashout"
        cancelLabel="Keep cashout"
        confirmTone="danger"
        onConfirm={() => {
          cancel.mutate();
          setCancelOpen(false);
        }}
      >
        This permanently deletes this cashout and any documents uploaded to it.
        This can&rsquo;t be undone.
      </ConfirmDialog>
    </div>
  );
}

/**
 * The post-verification prompt: once every document is verified the cashier
 * chooses between adding another document and closing the cashout out.
 */
function CompletePrompt({
  allVerified,
  pending,
  error,
  onComplete,
}: {
  allVerified: boolean;
  pending: boolean;
  error: unknown;
  onComplete: () => void;
}) {
  if (!allVerified) {
    return (
      <Card className="space-y-2">
        <Button className="w-full" disabled>
          Complete cashout
        </Button>
        <p className="text-ink-muted text-center text-xs">
          Verify every document above to complete the cashout.
        </p>
      </Card>
    );
  }

  return (
    <Card className="border-accent/40 space-y-3">
      <p className="flex items-center gap-2 font-medium">
        <CheckCircle2 className="text-success size-5" />
        All documents verified
      </p>
      <p className="text-ink-muted text-sm">
        Add another end-of-shift document, or complete the cashout to reconcile
        everything.
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          variant="outline"
          className="sm:flex-1"
          onClick={() =>
            document
              .getElementById("upload-zone")
              ?.scrollIntoView({ behavior: "smooth", block: "center" })
          }
        >
          <Plus className="size-4" />
          Add another document
        </Button>
        <Button className="sm:flex-1" loading={pending} onClick={onComplete}>
          Complete cashout
        </Button>
      </div>
      <ErrorBanner error={error} />
    </Card>
  );
}
