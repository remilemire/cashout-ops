// frontend/src/features/admin/cashoutDataTable.test.ts

import { describe, expect, it } from "vitest";

import type { CashoutDataRow } from "@/api/types";

import { MONEY_COLUMNS, columnTotals, sumMoney } from "./cashoutDataTable";
import type { MoneyColumnKey } from "./cashoutDataTable";

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
  function makeRow(
    id: string,
    money: Partial<Pick<CashoutDataRow, MoneyColumnKey>>,
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
      tipoutDepartments: ["kitchen"],
      barTipoutRate: "0.0500",
      kitchenTipoutRate: "0.0300",
      expoTipoutRate: "0.0100",
      hostTipoutRate: "0.0100",
      barTipout: null,
      kitchenTipout: null,
      expoTipout: null,
      hostTipout: null,
      cashOwedToHouse: null,
      cashOwedToEmployee: null,
      ...money,
      submissionId: `${id}-0000-0000`,
      submission: {
        id: `${id}-0000-0000`,
        businessDate: "2026-08-10",
        employee: {
          id: "user-ada",
          createdAt: "2026-07-01T00:00:00Z",
          email: "ada@test.com",
          fullName: "Ada Lovelace",
          role: "staff",
        },
      },
    };
  }

  it("totals every money column, null where no row has a value", () => {
    const rows = [
      makeRow("row-1", { kitchenTipout: "24.00", cashOwedToEmployee: "6.00" }),
      makeRow("row-2", { kitchenTipout: "18.10", barTipout: "5.00" }),
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
