// frontend/src/features/admin/cashoutDataTable.test.ts

import { describe, expect, it } from "vitest";

import type { CashoutDataRow, User } from "@/api/types";

import {
  MONEY_COLUMNS,
  columnTotals,
  csvFileName,
  csvRows,
  sumMoney,
} from "./cashoutDataTable";
import type { MoneyColumnKey } from "./cashoutDataTable";

const ada: User = {
  id: "user-ada",
  createdAt: "2026-07-01T00:00:00Z",
  email: "ada@test.com",
  fullName: "Ada Lovelace",
  role: "staff",
};

const grace: User = {
  id: "user-grace",
  createdAt: "2026-07-02T00:00:00Z",
  email: "grace@test.com",
  fullName: "Grace Hopper",
  role: "staff",
};

/** A row for Ada on 2026-08-10 with every money column null unless given. */
function makeRow(
  id: string,
  money: Partial<Pick<CashoutDataRow, MoneyColumnKey>>,
  submission: { employee?: User; businessDate?: string } = {},
): CashoutDataRow {
  return {
    id,
    createdAt: "2026-08-12T02:00:00Z",
    foodNetSales: "800.00",
    drinkNetSales: "400.00",
    totalNetSales: "1200.00",
    cardPaymentTotal: "1234.56",
    cashPaymentTotal: "150.00",
    cardTipTotal: "180.00",
    tipoutDepartments: ["kitchen", "manager"],
    barTipoutRate: "0.0500",
    kitchenTipoutRate: "0.0300",
    expoTipoutRate: "0.0100",
    hostTipoutRate: "0.0100",
    managerTipoutRate: "0.0100",
    barTipout: null,
    kitchenTipout: null,
    expoTipout: null,
    hostTipout: null,
    managerTipout: null,
    cashOwedToHouse: null,
    cashOwedToEmployee: null,
    ...money,
    submissionId: `${id}-0000-0000`,
    submission: {
      id: `${id}-0000-0000`,
      businessDate: submission.businessDate ?? "2026-08-10",
      employee: submission.employee ?? ada,
    },
  };
}

describe("sumMoney", () => {
  it("adds in exact cents", () => {
    // 0.1 + 0.2 in floating point is 0.30000000000000004.
    expect(sumMoney(["0.10", "0.20"])).toBe("0.30");
    expect(sumMoney(["1234.56", "0.44"])).toBe("1235.00");
  });

  it("always shows two decimals and no separators", () => {
    expect(sumMoney(["1000.00", "0.05"])).toBe("1000.05");
    expect(sumMoney(["0.00"])).toBe("0.00");
  });

  it("formats a negative total", () => {
    expect(sumMoney(["-10.50", "0.25"])).toBe("-10.25");
    expect(sumMoney(["-0.05"])).toBe("-0.05");
  });

  it("skips nulls", () => {
    expect(sumMoney([null, "24.00", null, "6.50"])).toBe("30.50");
  });

  it("is null when nothing was counted", () => {
    // A column nobody tipped out reads "—", not a misleading $0.00.
    expect(sumMoney([null, null])).toBeNull();
    expect(sumMoney([])).toBeNull();
  });
});

describe("columnTotals", () => {
  it("totals every money column, null where no row has a value", () => {
    const rows = [
      makeRow("row-1", {
        kitchenTipout: "24.00",
        managerTipout: "12.00",
        cashOwedToEmployee: "6.00",
      }),
      makeRow("row-2", {
        kitchenTipout: "18.10",
        barTipout: "5.00",
        managerTipout: "9.50",
      }),
      makeRow("row-3", {
        kitchenTipout: "0.20",
        barTipout: "2.25",
        cashOwedToHouse: "3.00",
      }),
    ];

    expect(columnTotals(rows)).toEqual({
      kitchenTipout: "42.30",
      barTipout: "7.25",
      expoTipout: null,
      hostTipout: null,
      managerTipout: "21.50",
      cashOwedToHouse: "3.00",
      cashOwedToEmployee: "6.00",
    });
  });

  it("is all null over no rows", () => {
    expect(columnTotals([])).toEqual({
      kitchenTipout: null,
      barTipout: null,
      expoTipout: null,
      hostTipout: null,
      managerTipout: null,
      cashOwedToHouse: null,
      cashOwedToEmployee: null,
    });
  });

  it("covers exactly the money columns, in table order", () => {
    expect(MONEY_COLUMNS.map((column) => column.key)).toEqual(
      Object.keys(columnTotals([])),
    );
  });
});

describe("csvRows", () => {
  const header = [
    "Employee",
    "Date",
    "Submission",
    "Kitchen tipout",
    "Bar tipout",
    "Expo tipout",
    "Host tipout",
    "Manager tipout",
    "Owed to house",
    "Owed to employee",
  ];

  it("lays out header, one row per data row, then the totals", () => {
    const rows = [
      makeRow("row-1", {
        kitchenTipout: "24.00",
        managerTipout: "12.00",
        cashOwedToEmployee: "6.00",
      }),
      makeRow(
        "row-2",
        { kitchenTipout: "18.10", barTipout: "5.00", cashOwedToHouse: "3.00" },
        { employee: grace, businessDate: "2026-08-11" },
      ),
    ];

    expect(csvRows(rows)).toEqual([
      header,
      // Raw ISO date and the full submission id, not the table's display
      // forms; blanks (not "—" or "0.00") where a department was not tipped.
      [
        "Ada Lovelace",
        "2026-08-10",
        "row-1-0000-0000",
        "24.00",
        "",
        "",
        "",
        "12.00",
        "",
        "6.00",
      ],
      [
        "Grace Hopper",
        "2026-08-11",
        "row-2-0000-0000",
        "18.10",
        "5.00",
        "",
        "",
        "",
        "3.00",
        "",
      ],
      ["Total", "", "", "42.10", "5.00", "", "", "12.00", "3.00", "6.00"],
    ]);
  });

  it("is header plus an all-blank totals row over no rows", () => {
    expect(csvRows([])).toEqual([
      header,
      ["Total", "", "", "", "", "", "", "", "", ""],
    ]);
  });
});

describe("csvFileName", () => {
  it("is the bare name with no filters", () => {
    expect(csvFileName({ date: "", employee: null })).toBe("cashout-data.csv");
  });

  it("appends the date filter", () => {
    expect(csvFileName({ date: "2026-08-10", employee: null })).toBe(
      "cashout-data-2026-08-10.csv",
    );
  });

  it("appends the employee filter as a slug", () => {
    expect(csvFileName({ date: "", employee: ada })).toBe(
      "cashout-data-ada-lovelace.csv",
    );
  });

  it("appends both, date first", () => {
    expect(csvFileName({ date: "2026-08-10", employee: ada })).toBe(
      "cashout-data-2026-08-10-ada-lovelace.csv",
    );
  });

  it("slugs accents and punctuation out of the employee name", () => {
    const zoe: User = { ...ada, id: "user-zoe", fullName: "Zoë O'Brien" };
    expect(csvFileName({ date: "", employee: zoe })).toBe(
      "cashout-data-zo-o-brien.csv",
    );
    const dashes: User = { ...ada, id: "user-dash", fullName: " -Ada- " };
    expect(csvFileName({ date: "", employee: dashes })).toBe(
      "cashout-data-ada.csv",
    );
  });
});
