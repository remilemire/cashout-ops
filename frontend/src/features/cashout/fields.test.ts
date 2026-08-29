// frontend/src/features/cashout/fields.test.ts

import { describe, expect, it } from "vitest";

import {
  CLASSIFICATION_SCHEMA_NAMES,
  SELECTABLE_CLASSIFICATIONS,
  fieldGroupsFor,
  fieldLabelFor,
  groupFields,
} from "./fields";

describe("groupFields", () => {
  it("orders TouchBistro fields into curated groups regardless of data order", () => {
    const groups = groupFields("TouchBistroReportData", {
      card_tip_total: "80.00",
      total_net_sales: "1500.00",
      cash_payment_total: "200.00",
      food_net_sales: "1000.00",
      card_transaction_count: 42,
      drink_net_sales: "500.00",
      card_payment_total: "1300.00",
    });

    expect(
      groups.map((group) => ({
        heading: group.heading,
        keys: group.fields.map((field) => field.key),
      })),
    ).toEqual([
      {
        heading: "Sales",
        keys: ["food_net_sales", "drink_net_sales", "total_net_sales"],
      },
      {
        heading: "Payments",
        keys: [
          "cash_payment_total",
          "card_payment_total",
          "card_transaction_count",
        ],
      },
      { heading: "Tips", keys: ["card_tip_total"] },
    ]);
  });

  it("drops curated fields absent from the data", () => {
    const groups = groupFields("TouchBistroReportData", {
      total_net_sales: "1500.00",
    });

    expect(groups).toEqual([
      {
        heading: "Sales",
        fields: [{ key: "total_net_sales", label: "Total net sales" }],
      },
    ]);
  });

  it("collects unknown keys into a trailing Other group", () => {
    const groups = groupFields("ServerSummaryReportData", {
      grand_total: "1234.56",
      mystery_field: "??",
    });

    expect(groups).toEqual([
      {
        heading: "Totals",
        fields: [{ key: "grand_total", label: "Grand total" }],
      },
      {
        heading: "Other",
        fields: [{ key: "mystery_field", label: "Mystery field" }],
      },
    ]);
  });

  it("falls back to one heading-less group for a null or unknown schema", () => {
    const data = { net_total: "9.99", itemCount: 3 };
    const expected = [
      {
        heading: null,
        fields: [
          { key: "net_total", label: "Net total" },
          { key: "itemCount", label: "Item count" },
        ],
      },
    ];

    expect(groupFields(null, data)).toEqual(expected);
    expect(groupFields("SomeFutureSchema", data)).toEqual(expected);
  });

  it("returns no groups for empty data", () => {
    expect(groupFields("TouchBistroReportData", {})).toEqual([]);
  });
});

describe("fieldGroupsFor", () => {
  it("returns the full TouchBistro groups regardless of any data", () => {
    const groups = fieldGroupsFor("TouchBistroReportData");

    expect(groups.map((group) => group.heading)).toEqual([
      "Sales",
      "Payments",
      "Tips",
    ]);
    expect(
      groups.flatMap((group) => group.fields.map((field) => field.key)),
    ).toEqual([
      "food_net_sales",
      "drink_net_sales",
      "total_net_sales",
      "cash_payment_total",
      "card_payment_total",
      "card_transaction_count",
      "card_tip_total",
    ]);
  });

  it("returns the full server-summary group", () => {
    expect(fieldGroupsFor("ServerSummaryReportData")).toEqual([
      {
        heading: "Totals",
        fields: [
          { key: "grand_total", label: "Grand total" },
          { key: "grand_total_transaction_count", label: "Orders" },
        ],
      },
    ]);
  });

  it("returns no groups for an unknown schema name", () => {
    expect(fieldGroupsFor("SomeFutureSchema")).toEqual([]);
  });
});

describe("CLASSIFICATION_SCHEMA_NAMES", () => {
  it("maps every selectable classification to a schema with curated groups", () => {
    for (const classification of SELECTABLE_CLASSIFICATIONS) {
      const schemaName = CLASSIFICATION_SCHEMA_NAMES[classification];
      expect(fieldGroupsFor(schemaName).length).toBeGreaterThan(0);
    }
  });
});

describe("fieldLabelFor", () => {
  it("returns the curated label for a known key", () => {
    expect(
      fieldLabelFor("ServerSummaryReportData", "grand_total_transaction_count"),
    ).toBe("Orders");
  });

  it("matches a dotted issue path on its first segment", () => {
    expect(fieldLabelFor("ServerSummaryReportData", "grand_total.amount")).toBe(
      "Grand total",
    );
  });

  it("falls back to the generic humanization for unknown keys or schemas", () => {
    expect(fieldLabelFor("ServerSummaryReportData", "mystery_field")).toBe(
      "Mystery field",
    );
    expect(fieldLabelFor(null, "grand_total_transaction_count")).toBe(
      "Grand total transaction count",
    );
  });
});
