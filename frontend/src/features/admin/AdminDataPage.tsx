// frontend/src/features/admin/AdminDataPage.tsx

import { useQuery } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { Link } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import type { CashoutData } from "@/api/types";
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

/**
 * The row's tipouts added up. Null when none was calculated — an unreconciled
 * cashout, or one that tipped out to nobody — so the cell reads "—" rather
 * than a misleading $0.00.
 */
function totalTipout(row: CashoutData): string | null {
  const amounts = [
    row.barTipout,
    row.kitchenTipout,
    row.expoTipout,
    row.hostTipout,
  ].filter((value): value is string => value != null);

  if (amounts.length === 0) return null;
  return amounts.reduce((sum, value) => sum + Number(value), 0).toFixed(2);
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
          <table className="w-full min-w-160 text-sm">
            <thead>
              <tr className="border-line text-ink-muted border-b text-left text-xs">
                <th className="px-4 py-2.5 font-medium">Created</th>
                <th className="px-4 py-2.5 font-medium">Submission</th>
                <th className="px-4 py-2.5 text-right font-medium">
                  Net sales
                </th>
                <th className="px-4 py-2.5 text-right font-medium">Tipouts</th>
                <th className="px-4 py-2.5 text-right font-medium">
                  Owed to house
                </th>
                <th className="px-4 py-2.5 text-right font-medium">
                  Owed to employee
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
                    {money(row.totalNetSales)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {money(totalTipout(row))}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {money(row.cashOwedToHouse)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {money(row.cashOwedToEmployee)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <p className="text-ink-muted text-xs">
        Figures populate once reconciliation is implemented; cashouts completed
        before then show no amounts.
      </p>
    </div>
  );
}
