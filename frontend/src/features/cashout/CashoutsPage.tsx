// frontend/src/features/cashout/CashoutsPage.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Plus, ReceiptText } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import { isNotFound } from "@/api/client";
import type { CashoutSubmissionListItem } from "@/api/types";
import { useAuth } from "@/auth/useAuth";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  PageHeader,
  SkeletonList,
} from "@/components/ui";
import { formatDate, formatDateTime } from "@/lib/format";

import { SubmissionStatusBadge } from "./status";

export function CashoutsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const submissionsQuery = useQuery({
    queryKey: cashoutKeys.submissions,
    queryFn: cashoutApi.listSubmissions,
  });

  // The submission awaiting cancel confirmation (drives the dialog).
  const [pendingCancel, setPendingCancel] =
    useState<CashoutSubmissionListItem | null>(null);

  const cancel = useMutation({
    mutationFn: (id: string) => cashoutApi.cancelSubmission(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
    },
    // Already gone (deleted elsewhere): refresh so the dead row disappears.
    onError: (error) => {
      if (isNotFound(error)) {
        void queryClient.invalidateQueries({
          queryKey: cashoutKeys.submissions,
        });
      }
    },
  });

  const startButton = (
    <Button onClick={() => navigate("/cashouts/new")}>
      <Plus className="size-4" />
      Start cashout
    </Button>
  );

  // The list endpoint returns everything for admins; this page is "mine".
  const mine = (submissionsQuery.data ?? []).filter(
    (submission) => submission.employeeUserId === user?.id,
  );

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="My cashouts"
        subtitle="End-of-shift cashout submissions."
        action={startButton}
      />
      <ErrorBanner error={submissionsQuery.error} />
      {/* The confirm dialog closes before the request settles, so a failed
          cancel must surface out here. */}
      <ErrorBanner error={cancel.error} />

      {submissionsQuery.isLoading ? (
        <SkeletonList />
      ) : mine.length === 0 ? (
        <EmptyState
          icon={<ReceiptText className="size-8" strokeWidth={1.5} />}
          title="No cashouts yet"
          hint="Start a cashout and upload your end-of-shift documents."
          action={startButton}
        />
      ) : (
        <ul className="space-y-2">
          {mine.map((submission) => (
            <li key={submission.id}>
              <Card
                padded={false}
                className="hover:border-accent/50 flex items-center gap-2 pr-3 transition-colors"
              >
                <Link
                  to={`/cashouts/${submission.id}`}
                  className="flex min-w-0 flex-1 items-center gap-3 p-4"
                >
                  <span className="bg-accent/10 text-accent-strong grid size-10 shrink-0 place-items-center rounded-lg">
                    <ReceiptText className="size-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      {formatDateTime(submission.submittedAt)}
                    </p>
                    <p className="text-ink-muted text-xs">
                      For {formatDate(submission.businessDate)} · #
                      {submission.id.slice(0, 8)}
                    </p>
                  </div>
                  <SubmissionStatusBadge status={submission.status} />
                </Link>
                {submission.status === "completed" ? (
                  <ChevronRight className="text-ink-muted size-4 shrink-0" />
                ) : (
                  <Button
                    variant="danger"
                    size="sm"
                    className="shrink-0"
                    onClick={() => setPendingCancel(submission)}
                  >
                    Cancel
                  </Button>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={pendingCancel !== null}
        onClose={() => setPendingCancel(null)}
        title="Cancel cashout?"
        confirmLabel="Cancel cashout"
        cancelLabel="Keep cashout"
        confirmTone="danger"
        onConfirm={() => {
          if (!pendingCancel) return;
          cancel.mutate(pendingCancel.id);
          setPendingCancel(null);
        }}
      >
        This removes cashout #{pendingCancel?.id.slice(0, 8)} and any documents
        uploaded to it. It can&rsquo;t be undone.
      </ConfirmDialog>
    </div>
  );
}
