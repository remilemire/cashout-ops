// frontend/src/features/admin/AdminSubmissionsPage.tsx

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ClipboardList } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import {
  Card,
  EmptyState,
  ErrorBanner,
  PageHeader,
  SkeletonList,
} from "@/components/ui";
import { SubmissionStatusBadge } from "@/features/cashout/status";
import { formatDateTime, initials } from "@/lib/format";

export function AdminSubmissionsPage() {
  const navigate = useNavigate();
  const submissionsQuery = useQuery({
    queryKey: cashoutKeys.submissions,
    queryFn: cashoutApi.listSubmissions,
  });
  const submissions = submissionsQuery.data ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="Submissions" subtitle="Every cashout, newest first." />
      <ErrorBanner error={submissionsQuery.error} />

      {submissionsQuery.isLoading ? (
        <SkeletonList count={5} />
      ) : submissions.length === 0 ? (
        <EmptyState
          icon={<ClipboardList className="size-8" strokeWidth={1.5} />}
          title="No submissions yet"
        />
      ) : (
        <Card padded={false} className="overflow-x-auto">
          <table className="w-full min-w-140 text-sm">
            <thead>
              <tr className="border-line text-ink-muted border-b text-left text-xs">
                <th className="px-4 py-2.5 font-medium">Submitted</th>
                <th className="px-4 py-2.5 font-medium">Cashier</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="w-8 px-2 py-2.5" aria-label="Open" />
              </tr>
            </thead>
            <tbody>
              {submissions.map((submission) => (
                <tr
                  key={submission.id}
                  onClick={() =>
                    navigate(`/admin/submissions/${submission.id}`)
                  }
                  className="border-line hover:bg-surface-2 cursor-pointer border-b transition-colors last:border-0"
                >
                  <td className="px-4 py-3">
                    <p className="font-medium">
                      {formatDateTime(submission.submittedAt)}
                    </p>
                    <p className="text-ink-muted text-xs">
                      #{submission.id.slice(0, 8)}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-2.5">
                      <span className="bg-accent/15 text-accent-strong grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold">
                        {initials(submission.submittedBy.fullName)}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-medium">
                          {submission.submittedBy.fullName}
                        </span>
                        <span className="text-ink-muted block truncate text-xs">
                          {submission.submittedBy.email}
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <SubmissionStatusBadge status={submission.status} />
                  </td>
                  <td className="px-2 py-3">
                    <ChevronRight className="text-ink-muted size-4" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
