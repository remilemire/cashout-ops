// frontend/src/features/cashout/SubmissionPage.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, PartyPopper } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import { isAdminRole, TIPOUT_DEPARTMENTS } from "@/api/types";
import type { TipoutDepartment } from "@/api/types";
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
import { cx } from "@/lib/cx";
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
  const [unsubmitOpen, setUnsubmitOpen] = useState(false);

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
    mutationFn: (tipoutDepartments: TipoutDepartment[]) =>
      cashoutApi.completeSubmission(submissionId, { tipoutDepartments }),
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

  const unsubmit = useMutation({
    mutationFn: () => cashoutApi.unsubmitSubmission(submissionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
    },
  });

  const submission = detailQuery.data;
  if (detailQuery.isLoading) return <FullScreenSpinner />;
  if (!submission) return <ErrorBanner error={detailQuery.error} />;

  // The employee and any admin have the same powers on a submission; the
  // admin-view presentation (back link, subtitle) keys on not being the
  // employee.
  const isEmployee = submission.employeeUserId === user?.id;
  const isAdminView = !isEmployee;
  const canAct = isEmployee || (user != null && isAdminRole(user.role));
  const editable = canAct && submission.status === "processing";
  // Cancel stays available until the cashout is completed.
  const canCancel = canAct && submission.status !== "completed";
  // Only an admin can reopen a completed cashout — never the employee alone.
  const canUnsubmit =
    user != null && isAdminRole(user.role) && submission.status === "completed";
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
        {canUnsubmit && (
          <Button
            variant="danger"
            size="sm"
            onClick={() => setUnsubmitOpen(true)}
          >
            Unsubmit
          </Button>
        )}
      </div>

      {/* The confirm dialogs close before the request settles, so a failed
          cancel or unsubmit must surface out here. */}
      <ErrorBanner error={cancel.error} />
      <ErrorBanner error={unsubmit.error} />

      <PageHeader
        title={`Cashout — ${formatDateTime(submission.submittedAt)}`}
        subtitle={
          isAdminView
            ? `Submitted by ${submission.employee.fullName} (${submission.employee.email})`
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
          initialSelected={submission.tipoutDepartments ?? []}
          pending={complete.isPending}
          error={complete.error}
          onComplete={(departments) => complete.mutate(departments)}
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
        This removes this cashout and any documents uploaded to it. It
        can&rsquo;t be undone.
      </ConfirmDialog>

      <ConfirmDialog
        open={unsubmitOpen}
        onClose={() => setUnsubmitOpen(false)}
        title="Unsubmit cashout?"
        confirmLabel="Unsubmit"
        cancelLabel="Keep completed"
        confirmTone="danger"
        onConfirm={() => {
          unsubmit.mutate();
          setUnsubmitOpen(false);
        }}
      >
        This reopens the cashout for editing and removes its reconciled data.
        Completing it again will regenerate the data.
      </ConfirmDialog>
    </div>
  );
}

const DEPARTMENT_LABELS: Record<TipoutDepartment, string> = {
  bar: "Bar",
  kitchen: "Kitchen",
  expo: "Expo",
  host: "Host",
};

/**
 * The post-verification prompt: once every document is verified the cashier
 * picks who this shift tips out to and closes the cashout, or keeps uploading
 * through the zone above it.
 */
function CompletePrompt({
  allVerified,
  initialSelected,
  pending,
  error,
  onComplete,
}: {
  allVerified: boolean;
  /** Seed for the checkboxes: the previous completion's departments, if any. */
  initialSelected: TipoutDepartment[];
  pending: boolean;
  error: unknown;
  onComplete: (tipoutDepartments: TipoutDepartment[]) => void;
}) {
  // The prompt only mounts once the detail payload is loaded, so the
  // initializer sees the fetched snapshot (kept through unsubmit).
  const [selected, setSelected] = useState<TipoutDepartment[]>(initialSelected);

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

  const toggle = (department: TipoutDepartment) =>
    setSelected((current) =>
      current.includes(department)
        ? current.filter((value) => value !== department)
        : [...current, department],
    );

  return (
    <Card className="border-accent/40 space-y-3">
      <p className="flex items-center gap-2 font-medium">
        <CheckCircle2 className="text-success size-5" />
        All documents verified
      </p>
      <p className="text-ink-muted text-sm">
        Add another end-of-shift document above, or complete the cashout to
        reconcile everything.
      </p>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Tip out to</legend>
        <p className="text-ink-muted text-xs">
          Select every department this shift tips out to. Each one is calculated
          at the rate in force today.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {TIPOUT_DEPARTMENTS.map((department) => {
            const checked = selected.includes(department);
            return (
              <label
                key={department}
                className={cx(
                  "flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm",
                  "transition-colors",
                  checked
                    ? "border-accent/40 bg-accent/10 font-medium"
                    : "border-line bg-surface-2",
                )}
              >
                <input
                  type="checkbox"
                  className="accent-accent size-4"
                  checked={checked}
                  onChange={() => toggle(department)}
                />
                {DEPARTMENT_LABELS[department]}
              </label>
            );
          })}
        </div>
      </fieldset>

      <Button
        className="w-full"
        loading={pending}
        onClick={() => onComplete(selected)}
      >
        Complete cashout
      </Button>
      <ErrorBanner error={error} />
    </Card>
  );
}
