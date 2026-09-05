// frontend/src/features/admin/cashoutDataTable.ts

import type { CashoutDataRow, User } from "@/api/types";

/**
 * The money columns of the admin cashout data table, in display order. Each
 * key is a `string | null` column of a row: a decimal amount serialized by the
 * backend ("24.00"), or null where the department was not tipped out / that
 * side of the cash balance is not owed.
 */
export const MONEY_COLUMNS = [
  { key: "kitchenTipout", label: "Kitchen tipout" },
  { key: "barTipout", label: "Bar tipout" },
  { key: "expoTipout", label: "Expo tipout" },
  { key: "hostTipout", label: "Host tipout" },
  { key: "managerTipout", label: "Manager tipout" },
  { key: "cashOwedToHouse", label: "Owed to house" },
  { key: "cashOwedToEmployee", label: "Owed to employee" },
] as const satisfies readonly { key: keyof CashoutDataRow; label: string }[];

export type MoneyColumnKey = (typeof MONEY_COLUMNS)[number]["key"];

/** Integer cents rendered as a plain "1234.56" / "-0.50" decimal string. */
function formatCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const magnitude = Math.abs(cents);
  const whole = Math.floor(magnitude / 100);
  const fraction = String(magnitude % 100).padStart(2, "0");
  return `${sign}${whole}.${fraction}`;
}

/**
 * Exact sum of decimal money strings, formatted like the backend's amounts:
 * two decimals, no currency symbol, no thousands separators. The arithmetic
 * runs in integer cents so "0.10" + "0.20" is "0.30", never a float artifact.
 *
 * Nulls are skipped, and a list with no non-null value sums to null rather
 * than "0.00": a column nobody tipped out should still read "—", not a
 * misleading $0.00.
 */
export function sumMoney(values: readonly (string | null)[]): string | null {
  let cents = 0;
  let counted = false;
  for (const value of values) {
    if (value == null) continue;
    cents += Math.round(Number(value) * 100);
    counted = true;
  }
  return counted ? formatCents(cents) : null;
}

/** One `sumMoney` per money column, over the given rows. */
export function columnTotals(
  rows: readonly CashoutDataRow[],
): Record<MoneyColumnKey, string | null> {
  return {
    kitchenTipout: sumMoney(rows.map((row) => row.kitchenTipout)),
    barTipout: sumMoney(rows.map((row) => row.barTipout)),
    expoTipout: sumMoney(rows.map((row) => row.expoTipout)),
    hostTipout: sumMoney(rows.map((row) => row.hostTipout)),
    managerTipout: sumMoney(rows.map((row) => row.managerTipout)),
    cashOwedToHouse: sumMoney(rows.map((row) => row.cashOwedToHouse)),
    cashOwedToEmployee: sumMoney(rows.map((row) => row.cashOwedToEmployee)),
  };
}

/**
 * The table as spreadsheet rows: a header, one row per data row, and the
 * totals row last. Amounts are bare numbers ("24.00", no "$") so spreadsheets
 * treat them as numbers, and a blank stands for "not tipped out", mirroring
 * the table's "—". The date is the raw YYYY-MM-DD, which spreadsheets parse
 * reliably, and the submission id is the full id rather than the table's
 * 8-character slice.
 */
export function csvRows(rows: readonly CashoutDataRow[]): string[][] {
  const totals = columnTotals(rows);
  return [
    [
      "Employee",
      "Date",
      "Submission",
      ...MONEY_COLUMNS.map((column) => column.label),
    ],
    ...rows.map((row) => [
      row.submission.employee.fullName,
      row.submission.businessDate,
      row.submissionId,
      ...MONEY_COLUMNS.map((column) => row[column.key] ?? ""),
    ]),
    [
      "Total",
      "",
      "",
      ...MONEY_COLUMNS.map((column) => totals[column.key] ?? ""),
    ],
  ];
}

/** "Zoë O'Brien" -> "zo-o-brien": lowercase, non-alphanumeric runs to "-". */
function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * The export's file name: "cashout-data" plus the filters in effect, e.g.
 * "cashout-data-2026-08-10-ada-lovelace.csv". The name describes what was
 * exported, so the export date is deliberately not part of it.
 */
export function csvFileName(filters: {
  date: string;
  employee: User | null;
}): string {
  const parts = ["cashout-data"];
  if (filters.date !== "") parts.push(filters.date);
  if (filters.employee != null) {
    const name = slug(filters.employee.fullName);
    if (name !== "") parts.push(name);
  }
  return `${parts.join("-")}.csv`;
}
