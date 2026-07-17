// frontend/src/features/admin/AdminDataPage.tsx

import { useQuery } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { Link } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import {
  Card,
  EmptyState,
  ErrorBanner,
  PageHeader,
  SkeletonList,
} from "@/components/ui";
import { formatDateTime } from "@/lib/format";

function money(value: string | null): string {
  return value != null ? `$${value}` : "—";
}

export function AdminDataPage() {
  const dataQuery = useQuery({
    queryKey: cashoutKeys.data,
    queryFn: cashoutApi.listData,
  });
  const rows = dataQuery.data ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Cashout data"
        subtitle="Reconciled totals from completed cashouts."
      />
      <ErrorBanner error={dataQuery.error} />

      {dataQuery.isLoading ? (
        <SkeletonList count={5} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<Database className="size-8" strokeWidth={1.5} />}
          title="No cashout data yet"
          hint="Data appears when cashouts are completed."
        />
      ) : (
        <Card padded={false} className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-line text-ink-muted border-b text-left text-xs">
                <th className="px-4 py-2.5 font-medium">Created</th>
                <th className="px-4 py-2.5 font-medium">Submission</th>
                <th className="px-4 py-2.5 text-right font-medium">
                  Daily tipout
                </th>
                <th className="px-4 py-2.5 text-right font-medium">
                  Net total
                </th>
                <th className="px-4 py-2.5 text-right font-medium">
                  Cash total
                </th>
                <th className="px-4 py-2.5 text-right font-medium">
                  Card total
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-line border-b last:border-0">
                  <td className="px-4 py-3">{formatDateTime(row.createdAt)}</td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/admin/submissions/${row.submissionId}`}
                      className="text-accent-strong font-medium hover:underline"
                    >
                      #{row.submissionId.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {money(row.dailyTipout)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {money(row.netTotal)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {money(row.cashTotal)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {money(row.cardTotal)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <p className="text-ink-muted text-xs">
        Totals populate once the extraction schemas are finalized.
      </p>
    </div>
  );
}
