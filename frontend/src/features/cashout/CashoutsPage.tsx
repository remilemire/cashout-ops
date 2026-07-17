// frontend/src/features/cashout/CashoutsPage.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Plus, ReceiptText } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import { useAuth } from "@/auth/AuthProvider";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  PageHeader,
  SkeletonList,
} from "@/components/ui";
import { formatDateTime } from "@/lib/format";

import { SubmissionStatusBadge } from "./status";

export function CashoutsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const submissionsQuery = useQuery({
    queryKey: cashoutKeys.submissions,
    queryFn: cashoutApi.listSubmissions,
  });

  const start = useMutation({
    mutationFn: cashoutApi.createSubmission,
    onSuccess: (submission) => {
      void queryClient.invalidateQueries({ queryKey: cashoutKeys.submissions });
      navigate(`/cashouts/${submission.id}`);
    },
  });

  const startButton = (
    <Button onClick={() => start.mutate()} loading={start.isPending}>
      <Plus className="size-4" />
      Start cashout
    </Button>
  );

  // The list endpoint returns everything for admins; this page is "mine".
  const mine = (submissionsQuery.data ?? []).filter(
    (submission) => submission.submittedByUserId === user?.id,
  );

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="My cashouts"
        subtitle="End-of-shift cashout submissions."
        action={startButton}
      />
      <ErrorBanner error={start.error ?? submissionsQuery.error} />

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
              <Link to={`/cashouts/${submission.id}`} className="group block">
                <Card className="group-hover:border-accent/50 flex items-center gap-3 transition-colors">
                  <span className="bg-accent/10 text-accent-strong grid size-10 shrink-0 place-items-center rounded-lg">
                    <ReceiptText className="size-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      {formatDateTime(submission.submittedAt)}
                    </p>
                    <p className="text-ink-muted text-xs">
                      #{submission.id.slice(0, 8)}
                    </p>
                  </div>
                  <SubmissionStatusBadge status={submission.status} />
                  <ChevronRight className="text-ink-muted size-4 shrink-0" />
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
