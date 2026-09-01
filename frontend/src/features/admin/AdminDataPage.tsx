// frontend/src/features/admin/AdminDataPage.tsx

import { useQuery } from "@tanstack/react-query";
import { Database, SearchX } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import type { CashoutDataRow, User } from "@/api/types";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Input,
  PageHeader,
  SkeletonList,
} from "@/components/ui";
import { formatDate } from "@/lib/format";

import { MONEY_COLUMNS, columnTotals } from "./cashoutDataTable";

/**
 * A tipout column is null for a department that was not tipped out, so the
 * cell reads "—" rather than a misleading $0.00.
 */
function money(value: string | null): string {
  return value != null ? `$${value}` : "—";
}

/** The distinct employees appearing in the rows, sorted by name. */
function distinctEmployees(rows: CashoutDataRow[]): User[] {
  const byId = new Map<string, User>();
  for (const row of rows) {
    byId.set(row.submission.employee.id, row.submission.employee);
  }
  return [...byId.values()].sort((a, b) =>
    a.fullName.localeCompare(b.fullName),
  );
}

export function AdminDataPage() {
  const dataQuery = useQuery({
    queryKey: cashoutKeys.data,
    queryFn: cashoutApi.listData,
  });
  const rows = dataQuery.data ?? [];

  // Client-side filters over the loaded rows: the endpoint returns the whole
  // (unpaginated) dataset, so there is nothing more to fetch.
  const [dateFilter, setDateFilter] = useState("");
  const [employeeFilter, setEmployeeFilter] = useState("");

  const employees = useMemo(
    () => distinctEmployees(dataQuery.data ?? []),
    [dataQuery.data],
  );

  const filteredRows = rows.filter(
    (row) =>
      (dateFilter === "" || row.submission.businessDate === dateFilter) &&
      (employeeFilter === "" || row.submission.employee.id === employeeFilter),
  );

  const totals = columnTotals(filteredRows);

  function clearFilters() {
    setDateFilter("");
    setEmployeeFilter("");
  }

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
        <>
          <div className="flex flex-wrap items-end gap-3">
            <label className="block w-44">
              <span className="mb-1 block text-sm font-medium">Date</span>
              <Input
                type="date"
                value={dateFilter}
                onChange={(event) => setDateFilter(event.target.value)}
              />
            </label>
            <label className="block w-56">
              <span className="mb-1 block text-sm font-medium">Employee</span>
              <select
                className="bg-surface border-line focus:ring-accent/50 h-11 w-full rounded-lg border px-3 text-sm outline-none focus:ring-2"
                value={employeeFilter}
                onChange={(event) => setEmployeeFilter(event.target.value)}
              >
                <option value="">All employees</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.fullName}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {filteredRows.length === 0 ? (
            <EmptyState
              icon={<SearchX className="size-8" strokeWidth={1.5} />}
              title="No rows match the filters"
              hint="Try another day or employee."
              action={
                <Button variant="outline" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <Card padded={false} className="overflow-x-auto">
              <table className="w-full min-w-230 text-sm">
                <thead>
                  <tr className="border-line text-ink-muted border-b text-left text-xs">
                    <th className="px-4 py-2.5 font-medium">Employee</th>
                    <th className="px-4 py-2.5 font-medium">Date</th>
                    <th className="px-4 py-2.5 font-medium">Submission</th>
                    {MONEY_COLUMNS.map((column) => (
                      <th
                        key={column.key}
                        className="px-4 py-2.5 text-right font-medium"
                      >
                        {column.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((row) => (
                    <tr
                      key={row.id}
                      className="border-line border-b last:border-0"
                    >
                      <td className="px-4 py-3">
                        {row.submission.employee.fullName}
                      </td>
                      <td className="px-4 py-3">
                        {formatDate(row.submission.businessDate)}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          to={`/admin/submissions/${row.submissionId}`}
                          className="text-accent-strong font-medium hover:underline"
                        >
                          #{row.submissionId.slice(0, 8)}
                        </Link>
                      </td>
                      {MONEY_COLUMNS.map((column) => (
                        <td
                          key={column.key}
                          className="px-4 py-3 text-right tabular-nums"
                        >
                          {money(row[column.key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  {/* Totals of the rows on screen, so they follow the filters. */}
                  <tr className="border-line border-t-2 font-semibold">
                    <th scope="row" className="px-4 py-3 text-left">
                      Total
                    </th>
                    <td colSpan={2} />
                    {MONEY_COLUMNS.map((column) => (
                      <td
                        key={column.key}
                        className="px-4 py-3 text-right tabular-nums"
                      >
                        {money(totals[column.key])}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
