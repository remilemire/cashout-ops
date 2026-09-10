import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cashoutApi } from "@/api/cashout";
import type { CashoutDataRow, User } from "@/api/types";
import { downloadCsv } from "@/lib/csv";
import { formatDate } from "@/lib/format";

import { AdminDataPage } from "./AdminDataPage";

vi.mock("@/api/cashout", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/cashout")>();
  return {
    ...actual,
    cashoutApi: {
      ...actual.cashoutApi,
      listData: vi.fn(),
    },
  };
});

// The download's own tests cover the blob/anchor mechanics; here it is just
// the call the page makes.
vi.mock("@/lib/csv", () => ({ downloadCsv: vi.fn() }));

const listDataMock = vi.mocked(cashoutApi.listData);
const downloadCsvMock = vi.mocked(downloadCsv);

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

function makeRow(
  id: string,
  employee: User,
  businessDate: string,
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
    depositTotal: null,
    adjustmentNote: null,
    tipoutDepartments: ["kitchen", "manager"],
    barTipoutRate: "0.0500",
    kitchenTipoutRate: "0.0300",
    expoTipoutRate: "0.0100",
    hostTipoutRate: "0.0100",
    managerTipoutRate: "0.0100",
    barTipout: null,
    kitchenTipout: "24.00",
    expoTipout: null,
    hostTipout: null,
    managerTipout: "12.00",
    cashOwedToHouse: "6.00",
    cashOwedToEmployee: null,
    // Distinct within the first 8 characters: the table shows a #-prefixed
    // 8-character slice as the link text.
    submissionId: `${id}-0000-0000`,
    submission: {
      id: `${id}-0000-0000`,
      businessDate,
      employee,
    },
  };
}

// Ada appears on two days and shares one day with Grace, so each filter
// (and their combination) narrows to a different subset.
const adaAug10 = makeRow("row-1", ada, "2026-08-10");
const rows: CashoutDataRow[] = [
  adaAug10,
  makeRow("row-2", grace, "2026-08-11"),
  makeRow("row-3", ada, "2026-08-11"),
];

const AUG_10 = formatDate("2026-08-10");
const AUG_11 = formatDate("2026-08-11");

const CSV_HEADER = [
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

/** The CSV line for a fixture row: raw date and full id, blanks for null. */
function csvLine(row: CashoutDataRow): string[] {
  return [
    row.submission.employee.fullName,
    row.submission.businessDate,
    row.submissionId,
    "24.00",
    "",
    "",
    "",
    "12.00",
    "6.00",
    "",
  ];
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(
    [{ path: "/admin/data", element: <AdminDataPage /> }],
    { initialEntries: ["/admin/data"] },
  );

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

/** The table's totals row: the one headed by the "Total" row header. */
function totalsRow(): HTMLTableRowElement {
  const row = screen.getByRole("rowheader", { name: "Total" }).closest("tr");
  if (row == null) throw new Error("totals row header is not in a row");
  return row;
}

beforeEach(() => {
  listDataMock.mockReset();
  listDataMock.mockResolvedValue(rows);
  downloadCsvMock.mockReset();
});

describe("AdminDataPage", () => {
  it("shows each row's employee and business date", async () => {
    renderPage();

    // Cell queries throughout: the employee names also appear as options in
    // the filter select, and the dates as the column header / filter label.
    expect(
      await screen.findAllByRole("cell", { name: "Ada Lovelace" }),
    ).toHaveLength(2);
    expect(screen.getByRole("cell", { name: "Grace Hopper" })).toBeDefined();
    expect(screen.getAllByRole("cell", { name: AUG_10 })).toHaveLength(1);
    expect(screen.getAllByRole("cell", { name: AUG_11 })).toHaveLength(2);
  });

  it("shows each department's tipout, dash for the untipped", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    for (const department of ["Kitchen", "Bar", "Expo", "Host", "Manager"]) {
      expect(
        screen.getByRole("columnheader", { name: `${department} tipout` }),
      ).toBeDefined();
    }
    // Every fixture row tips out to the kitchen (and the manager, as every
    // cashout does): the other departments read "—", not a misleading $0.00.
    expect(screen.getAllByRole("cell", { name: "$24.00" })).toHaveLength(
      rows.length,
    );
    expect(screen.getAllByRole("cell", { name: "$12.00" })).toHaveLength(
      rows.length,
    );
    expect(
      screen.getAllByRole("cell", { name: "—" }).length,
    ).toBeGreaterThanOrEqual(rows.length * 3);
  });

  it("totals the money columns, dash where no row has a value", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    const cells = within(totalsRow())
      .getAllByRole("cell")
      .map((cell) => cell.textContent);

    // The empty cell spans the Date and Submission columns; the sums follow
    // in column order: kitchen, bar, expo, host, manager, owed to house, owed
    // to employee. Never-tipped columns read "—", not $0.00.
    expect(cells).toEqual([
      "",
      "$72.00",
      "—",
      "—",
      "—",
      "$36.00",
      "$18.00",
      "—",
    ]);
  });

  it("totals only the rows left by the date filter", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    fireEvent.change(screen.getByLabelText("Date"), {
      target: { value: "2026-08-10" },
    });

    const totals = within(totalsRow());
    expect(totals.getByRole("cell", { name: "$24.00" })).toBeDefined();
    expect(totals.getByRole("cell", { name: "$6.00" })).toBeDefined();
    expect(totals.queryByRole("cell", { name: "$72.00" })).toBeNull();
  });

  it("totals only the rows left by the employee filter", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    fireEvent.change(screen.getByLabelText("Employee"), {
      target: { value: grace.id },
    });

    const totals = within(totalsRow());
    expect(totals.getByRole("cell", { name: "$24.00" })).toBeDefined();
    expect(totals.getByRole("cell", { name: "$6.00" })).toBeDefined();
    expect(totals.queryByRole("cell", { name: "$72.00" })).toBeNull();
  });

  it("exports the visible rows as CSV", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(downloadCsvMock).toHaveBeenCalledOnce();
    expect(downloadCsvMock).toHaveBeenCalledWith("cashout-data.csv", [
      CSV_HEADER,
      ...rows.map(csvLine),
      ["Total", "", "", "72.00", "", "", "", "36.00", "18.00", ""],
    ]);
  });

  it("names the export after the filters and exports only the matching rows", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    fireEvent.change(screen.getByLabelText("Date"), {
      target: { value: "2026-08-10" },
    });
    fireEvent.change(screen.getByLabelText("Employee"), {
      target: { value: ada.id },
    });
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(downloadCsvMock).toHaveBeenCalledOnce();
    expect(downloadCsvMock).toHaveBeenCalledWith(
      "cashout-data-2026-08-10-ada-lovelace.csv",
      [
        CSV_HEADER,
        csvLine(adaAug10),
        ["Total", "", "", "24.00", "", "", "", "12.00", "6.00", ""],
      ],
    );
  });

  it("prints the page", async () => {
    // jsdom's window.print is a not-implemented stub.
    const printSpy = vi.spyOn(window, "print").mockImplementation(() => {});
    try {
      renderPage();
      await screen.findAllByRole("cell", { name: "Ada Lovelace" });

      fireEvent.click(screen.getByRole("button", { name: "Print" }));

      expect(printSpy).toHaveBeenCalledOnce();
    } finally {
      printSpy.mockRestore();
    }
  });

  it("disables export and print when no rows match", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    fireEvent.change(screen.getByLabelText("Date"), {
      target: { value: "2026-01-01" },
    });

    const exportButton = screen.getByRole<HTMLButtonElement>("button", {
      name: "Export CSV",
    });
    const printButton = screen.getByRole<HTMLButtonElement>("button", {
      name: "Print",
    });
    expect(exportButton.disabled).toBe(true);
    expect(printButton.disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(exportButton.disabled).toBe(false);
    expect(printButton.disabled).toBe(false);
  });

  it("keeps the submission links intact", async () => {
    renderPage();

    const link = await screen.findByRole("link", { name: "#row-1-00" });
    expect(link.getAttribute("href")).toBe(
      "/admin/submissions/row-1-0000-0000",
    );
  });

  it("narrows the rows to the picked business date", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    fireEvent.change(screen.getByLabelText("Date"), {
      target: { value: "2026-08-10" },
    });

    expect(screen.getAllByRole("cell", { name: "Ada Lovelace" })).toHaveLength(
      1,
    );
    expect(screen.queryByRole("cell", { name: "Grace Hopper" })).toBeNull();
    expect(screen.queryByRole("cell", { name: AUG_11 })).toBeNull();
  });

  it("narrows the rows to the picked employee", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    fireEvent.change(screen.getByLabelText("Employee"), {
      target: { value: grace.id },
    });

    expect(screen.getByRole("cell", { name: "Grace Hopper" })).toBeDefined();
    expect(screen.queryByRole("cell", { name: "Ada Lovelace" })).toBeNull();
    expect(screen.queryByRole("cell", { name: AUG_10 })).toBeNull();
  });

  it("offers the distinct employees sorted by name", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    const options = screen
      .getAllByRole<HTMLOptionElement>("option")
      .map((option) => option.textContent);

    // One entry per employee, however many rows each has.
    expect(options).toEqual(["All employees", "Ada Lovelace", "Grace Hopper"]);
  });

  it("shows the no-match state and restores the rows on clear", async () => {
    renderPage();
    await screen.findAllByRole("cell", { name: "Ada Lovelace" });

    fireEvent.change(screen.getByLabelText("Date"), {
      target: { value: "2026-01-01" },
    });

    expect(screen.getByText("No rows match the filters")).toBeDefined();
    expect(screen.queryByRole("cell", { name: "Ada Lovelace" })).toBeNull();
    // A dataset filtered to nothing is not an empty dataset.
    expect(screen.queryByText("No cashout data yet")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(screen.getAllByRole("cell", { name: "Ada Lovelace" })).toHaveLength(
      2,
    );
    expect(screen.getByRole("cell", { name: "Grace Hopper" })).toBeDefined();
    expect(screen.queryByText("No rows match the filters")).toBeNull();
  });

  it("keeps the genuine empty state for an empty dataset", async () => {
    listDataMock.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText("No cashout data yet")).toBeDefined();
    // No filter bar when there is nothing to filter, and nothing to export
    // or print either.
    expect(screen.queryByLabelText("Date")).toBeNull();
    expect(screen.queryByRole("button", { name: "Export CSV" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Print" })).toBeNull();
  });
});
