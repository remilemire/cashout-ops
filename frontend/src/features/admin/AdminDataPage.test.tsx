// frontend/src/features/admin/AdminDataPage.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cashoutApi } from "@/api/cashout";
import type { CashoutDataRow, User } from "@/api/types";
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

const listDataMock = vi.mocked(cashoutApi.listData);

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
    tipoutDepartments: ["kitchen"],
    barTipoutRate: "0.0500",
    kitchenTipoutRate: "0.0300",
    expoTipoutRate: "0.0100",
    hostTipoutRate: "0.0100",
    barTipout: null,
    kitchenTipout: "24.00",
    expoTipout: null,
    hostTipout: null,
    cashOwedToHouse: null,
    cashOwedToEmployee: "30.00",
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
const rows: CashoutDataRow[] = [
  makeRow("row-1", ada, "2026-08-10"),
  makeRow("row-2", grace, "2026-08-11"),
  makeRow("row-3", ada, "2026-08-11"),
];

const AUG_10 = formatDate("2026-08-10");
const AUG_11 = formatDate("2026-08-11");

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

beforeEach(() => {
  listDataMock.mockReset();
  listDataMock.mockResolvedValue(rows);
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
    // No filter bar when there is nothing to filter.
    expect(screen.queryByLabelText("Date")).toBeNull();
  });
});
