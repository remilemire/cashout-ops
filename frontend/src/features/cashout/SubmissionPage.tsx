// frontend/src/features/cashout/SubmissionPage.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, PartyPopper } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import { ApiError, isNotFound } from "@/api/client";
import { isAdminRole, SELECTABLE_TIPOUT_DEPARTMENTS } from "@/api/types";
import type {
  CashoutUpload,
  CompleteSubmissionInput,
  ErrorCode,
  ManualEntryInput,
  TipoutDepartment,
} from "@/api/types";
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
  TextField,
} from "@/components/ui";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";

import { AdjustmentForm } from "./AdjustmentForm";
import { DataCard } from "./DataCard";
import { UploadCard } from "./UploadCard";
import { ManualEntryDialog } from "./ManualEntryDialog";
import { UploadZone } from "./UploadZone";
import { SubmissionStatusBadge } from "./status";

export function SubmissionPage() {
  const { submissionId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [unsubmitOpen, setUnsubmitOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);

  const detailQuery = useQuery({
    queryKey: cashoutKeys.submission(submissionId),
    queryFn: () => cashoutApi.getSubmission(submissionId),
    enabled: submissionId !== "",
  });

  // A 404 from any action means the cashout (or an upload on it) was deleted
  // elsewhere — another tab, or an admin. Refetch so the page reports the
  // death instead of keeping stale, unactionable state.
  const refreshIfGone = (error: unknown) => {
    if (isNotFound(error)) {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
    }
  };

  const createUpload = useMutation({
    mutationFn: (file: File) => cashoutApi.createUpload(submissionId, file),
    onSuccess: (analysis) => {
      queryClient.setQueryData(cashoutKeys.analysis(analysis.id), analysis);
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
    onError: refreshIfGone,
  });

  const manualUpload = useMutation({
    mutationFn: ({ file, input }: { file: File; input: ManualEntryInput }) =>
      cashoutApi.createManualUpload(submissionId, file, input),
    onSuccess: (analysis) => {
      queryClient.setQueryData(cashoutKeys.analysis(analysis.id), analysis);
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
      setManualOpen(false);
    },
    onError: refreshIfGone,
  });

  const complete = useMutation({
    mutationFn: (input: CompleteSubmissionInput) =>
      cashoutApi.completeSubmission(submissionId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
      // The completed banner renders at the top; the button sits at the bottom.
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    onError: refreshIfGone,
  });

  const cancel = useMutation({
    mutationFn: () => cashoutApi.cancelSubmission(submissionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
      navigate("/cashouts");
    },
    // Already gone (deleted elsewhere): the outcome the user wanted, so land
    // where a successful cancel lands rather than surfacing a failure.
    onError: (error) => {
      if (isNotFound(error)) {
        void queryClient.invalidateQueries({
          queryKey: cashoutKeys.submissions,
        });
        navigate("/cashouts");
      }
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
    onError: refreshIfGone,
  });

  const updateDate = useMutation({
    mutationFn: (businessDate: string) =>
      cashoutApi.updateSubmission(submissionId, { businessDate }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
      // The cashier's list renders "For {date}".
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
    },
    onError: refreshIfGone,
  });

  const submission = detailQuery.data;
  const isAdminUser = user != null && isAdminRole(user.role);
  if (detailQuery.isLoading) return <FullScreenSpinner />;
  // Checked before the cached data: a cashout deleted while on this page
  // leaves stale data behind, and every action on it would fail.
  if (isNotFound(detailQuery.error)) {
    return (
      <div className="mx-auto max-w-2xl">
        <EmptyState
          title="Cashout not found"
          hint="This cashout no longer exists — it may have been cancelled."
          action={
            <Link
              to={isAdminUser ? "/admin/submissions" : "/cashouts"}
              className="text-accent-strong inline-flex items-center gap-1 text-sm hover:underline"
            >
              <ArrowLeft className="size-4" />
              {isAdminUser ? "All submissions" : "My cashouts"}
            </Link>
          }
        />
      </div>
    );
  }
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
  const uploads = inUploadOrder(submission.uploads);
  // Every document found in every upload counts on its own; completing needs
  // all of them verified, and an upload with nothing found yet holds it up.
  const analyses = uploads.flatMap((upload) => upload.analyses);
  const verifiedCount = analyses.filter(
    (analysis) => analysis.status === "verified",
  ).length;
  const allVerified =
    uploads.length > 0 &&
    uploads.every(
      (upload) =>
        upload.analyses.length > 0 &&
        upload.analyses.every((analysis) => analysis.status === "verified"),
    );

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
            {uploads.length > 0 && submission.status === "processing" && (
              <Badge tone={allVerified ? "success" : "neutral"}>
                {verifiedCount}/{analyses.length} verified
              </Badge>
            )}
            <SubmissionStatusBadge status={submission.status} />
          </div>
        }
      />

      <BusinessDateField
        // Keyed by the saved day so the draft resets whenever it changes —
        // after a save, an unsubmit, or a refetch — but survives a failed save.
        key={submission.businessDate}
        value={submission.businessDate}
        editable={editable}
        pending={updateDate.isPending}
        error={updateDate.error}
        onSave={(businessDate) => updateDate.mutate(businessDate)}
        onRevert={() => updateDate.reset()}
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

      {uploads.length === 0 && !editable && <EmptyState title="No uploads" />}

      {uploads.map((upload) => (
        <UploadCard
          key={upload.id}
          upload={upload}
          submissionId={submission.id}
          editable={editable}
        />
      ))}

      {editable && (
        <UploadZone
          onFile={(file) => createUpload.mutate(file)}
          pending={createUpload.isPending}
          error={createUpload.error}
          onManualEntry={() => setManualOpen(true)}
        />
      )}

      {editable && uploads.length > 0 && (
        <CompletePrompt
          allVerified={allVerified}
          initialSelected={selectableDepartments(
            submission.tipoutDepartments ?? [],
          )}
          canAdjust={isAdminUser}
          pending={complete.isPending}
          error={complete.error}
          onComplete={(input) => complete.mutate(input)}
        />
      )}

      <ManualEntryDialog
        withFile
        open={manualOpen}
        onClose={() => setManualOpen(false)}
        pending={manualUpload.isPending}
        error={manualUpload.error}
        onSubmit={(input, file) => {
          if (file) manualUpload.mutate({ file, input });
        }}
      />

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

/**
 * The uploads oldest-first. The detail payload carries them in no guaranteed
 * order, and an upload whose analysis was just re-extracted or verified can
 * come back in a different position — which reshuffles the cards under the
 * cashier mid-verification. Ids break a tie between two uploads created in
 * the same instant, so the order is total.
 */
function inUploadOrder(uploads: CashoutUpload[]): CashoutUpload[] {
  return [...uploads].sort(
    (a, b) =>
      Date.parse(a.createdAt) - Date.parse(b.createdAt) ||
      a.id.localeCompare(b.id),
  );
}

const DEPARTMENT_LABELS: Record<TipoutDepartment, string> = {
  bar: "Bar",
  kitchen: "Kitchen",
  expo: "Expo",
  host: "Host",
  manager: "Manager",
};

/**
 * The cashier's part of a department list. A last-completion snapshot also
 * names the manager, whom the server adds to every completion; the form
 * neither shows nor sends that one.
 */
function selectableDepartments(
  departments: TipoutDepartment[],
): TipoutDepartment[] {
  return departments.filter((department) =>
    SELECTABLE_TIPOUT_DEPARTMENTS.includes(department),
  );
}

/**
 * What to go and look at when reconciliation refuses the cashout. The banner
 * carries the backend's message, which cannot name the documents; these point
 * at the ones on this page, by the field labels their verification forms
 * render.
 */
const RECONCILE_HINTS: Partial<Record<ErrorCode, string>> = {
  RECONCILE_TOUCHBISTRO_MISSING:
    "Upload the TouchBistro end-of-day report, or add it with manual entry.",
  RECONCILE_TOUCHBISTRO_DUPLICATE:
    "Remove the extra TouchBistro report — a cashout reconciles against one.",
  RECONCILE_CARD_PAYMENT_MISMATCH:
    "Compare Card payments on the TouchBistro report against the Grand total on each server summary; they have to add up.",
  RECONCILE_CARD_TRANSACTION_MISMATCH:
    "Compare Card orders on the TouchBistro report against Orders on each server summary; they have to add up.",
  RECONCILE_DOCUMENT_DATA_INVALID:
    "Re-verify the document you last corrected: one of its values can no longer be read as a number.",
};

function reconcileHint(error: unknown): string | undefined {
  return error instanceof ApiError ? RECONCILE_HINTS[error.code] : undefined;
}

/** Whether completing was refused because the card payments do not add up. */
function isCardMismatch(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.code === "RECONCILE_CARD_PAYMENT_MISMATCH"
  );
}

/** The adjustment form's own controls; a validation issue on one shows there. */
const ADJUSTMENT_FIELDS = new Set(["depositTotal", "note"]);

/**
 * The post-verification prompt: once every document is verified the cashier
 * picks who this shift tips out to and closes the cashout, or keeps uploading
 * through the zone above it.
 */
function CompletePrompt({
  allVerified,
  initialSelected,
  canAdjust,
  pending,
  error,
  onComplete,
}: {
  allVerified: boolean;
  /** Seed for the checkboxes: the previous completion's departments, if any. */
  initialSelected: TipoutDepartment[];
  /** Whether the viewer may record a deposit adjustment (admins only). */
  canAdjust: boolean;
  pending: boolean;
  error: unknown;
  onComplete: (input: CompleteSubmissionInput) => void;
}) {
  // The prompt only mounts once the detail payload is loaded, so the
  // initializer sees the fetched snapshot (kept through unsubmit).
  const [selected, setSelected] = useState<TipoutDepartment[]>(initialSelected);
  const [depositTotal, setDepositTotal] = useState("");
  const [note, setNote] = useState("");
  const hint = reconcileHint(error);
  // The adjustment is a remedy for one refusal, so it appears only after
  // that one — and stays while it carries a value, through any later error.
  const showAdjustment =
    canAdjust && (isCardMismatch(error) || depositTotal !== "");
  // A validation failure that landed entirely on the adjustment's own fields
  // surfaces under them; anything else falls back to the banner.
  const bannerError =
    showAdjustment &&
    error instanceof ApiError &&
    error.issues.length > 0 &&
    error.issues.every((issue) =>
      ADJUSTMENT_FIELDS.has(String(issue.path.at(-1))),
    )
      ? null
      : error;

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

  const submit = () => {
    const deposit = depositTotal.trim();
    const trimmedNote = note.trim();
    onComplete({
      tipoutDepartments: selected,
      // Only an admin's non-empty deposit becomes an adjustment; the note
      // rides along with it and is dropped when blank.
      ...(canAdjust &&
        deposit !== "" && {
          adjustment: {
            depositTotal: deposit,
            ...(trimmedNote !== "" && { note: trimmedNote }),
          },
        }),
    });
  };

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
          at the rate in force today. The manager is tipped out on every
          cashout, on top of the departments you select.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {SELECTABLE_TIPOUT_DEPARTMENTS.map((department) => {
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

      {showAdjustment && (
        <AdjustmentForm
          depositTotal={depositTotal}
          note={note}
          onChange={(next) => {
            setDepositTotal(next.depositTotal);
            setNote(next.note);
          }}
          error={error}
        />
      )}

      <Button className="w-full" loading={pending} onClick={submit}>
        Complete cashout
      </Button>
      <ErrorBanner error={bannerError} />
      {hint != null && <p className="text-ink-muted text-xs">{hint}</p>}
    </Card>
  );
}

/**
 * The same "Cashout for" control as the new-cashout page, live until the
 * cashout is completed (an unsubmit reopens it). Saving is explicit rather
 * than on change: a date input emits intermediate values while a year is
 * typed, and each one would otherwise become a request.
 */
function BusinessDateField({
  value,
  editable,
  pending,
  error,
  onSave,
  onRevert,
}: {
  /** The saved day (YYYY-MM-DD). */
  value: string;
  editable: boolean;
  pending: boolean;
  error: unknown;
  onSave: (businessDate: string) => void;
  /** The draft was discarded; a stale save error should go with it. */
  onRevert: () => void;
}) {
  const [draft, setDraft] = useState(value);
  const dirty = draft !== "" && draft !== value;
  const revert = () => {
    setDraft(value);
    onRevert();
  };

  return (
    <div className="space-y-2">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (dirty) onSave(draft);
        }}
      >
        <div className="w-44">
          <TextField
            label="Cashout for"
            type="date"
            value={draft}
            disabled={!editable}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") revert();
            }}
          />
        </div>
        {editable && dirty && (
          <>
            <Button type="submit" size="sm" loading={pending}>
              Save
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={revert}>
              Revert
            </Button>
          </>
        )}
      </form>
      <ErrorBanner error={error} />
    </div>
  );
}
