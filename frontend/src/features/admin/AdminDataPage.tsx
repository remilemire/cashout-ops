import { useQuery } from "@tanstack/react-query";
import { Database, Download, Printer, SearchX } from "lucide-react";
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
import { downloadCsv } from "@/lib/csv";
import { formatDate } from "@/lib/format";

import {
  MONEY_COLUMNS,
  columnTotals,
  csvFileName,
  csvRows,
} from "./cashoutDataTable";

// Cell classes, with the print tightening in one place: the ten-column
// table has to fit a portrait page. On screen nothing changes.
const HEADER_CELL = "px-4 py-2.5 font-medium print:px-2";
const MONEY_HEADER_CELL = `${HEADER_CELL} text-right`;
const CELL = "px-4 py-3 print:px-2 print:py-1.5";
const MONEY_CELL = `${CELL} text-right tabular-nums`;

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

  const selectedEmployee =
    employees.find((employee) => employee.id === employeeFilter) ?? null;

  function clearFilters() {
    setDateFilter("");
    setEmployeeFilter("");
  }

  // The export is what is on screen: the filtered rows, named after the
  // filters that produced them.
  function exportCsv() {
    downloadCsv(
      csvFileName({ date: dateFilter, employee: selectedEmployee }),
      csvRows(filteredRows),
    );
  }

  // Export and print mirror the table branch below: nothing to offer while
  // loading or for a dataset with no rows at all, and nothing to act on when
  // the filters match no row.
  const hasData = !dataQuery.isLoading && rows.length > 0;
  const nothingMatches = filteredRows.length === 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Cashout data"
        subtitle="Reconciled totals from completed cashouts."
        action={
          hasData && (
            <div className="flex gap-2 print:hidden">
              <Button
                variant="outline"
                size="sm"
                onClick={exportCsv}
                disabled={nothingMatches}
              >
                <Download className="size-4" />
                Export CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.print()}
                disabled={nothingMatches}
              >
                <Printer className="size-4" />
                Print
              </Button>
            </div>
          )
        }
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
          <div className="flex flex-wrap items-end gap-3 print:hidden">
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
            <Card
              padded={false}
              className="overflow-x-auto print:overflow-visible print:rounded-none print:border-0 print:shadow-none"
            >
              <table className="w-full min-w-230 text-sm print:min-w-0 print:text-xs">
                <thead>
                  <tr className="border-line text-ink-muted border-b text-left text-xs">
                    <th className={HEADER_CELL}>Employee</th>
                    <th className={HEADER_CELL}>Date</th>
                    <th className={HEADER_CELL}>Submission</th>
                    {MONEY_COLUMNS.map((column) => (
                      <th key={column.key} className={MONEY_HEADER_CELL}>
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
                      <td className={CELL}>
                        {row.submission.employee.fullName}
                      </td>
                      <td className={CELL}>
                        {formatDate(row.submission.businessDate)}
                      </td>
                      <td className={CELL}>
                        <Link
                          to={`/admin/submissions/${row.submissionId}`}
                          className="text-accent-strong font-medium hover:underline"
                        >
                          #{row.submissionId.slice(0, 8)}
                        </Link>
                      </td>
                      {MONEY_COLUMNS.map((column) => (
                        <td key={column.key} className={MONEY_CELL}>
                          {money(row[column.key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  {/* Totals of the rows on screen, so they follow the filters. */}
                  <tr className="border-line border-t-2 font-semibold">
                    <th scope="row" className={`${CELL} text-left`}>
                      Total
                    </th>
                    <td colSpan={2} />
                    {MONEY_COLUMNS.map((column) => (
                      <td key={column.key} className={MONEY_CELL}>
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
