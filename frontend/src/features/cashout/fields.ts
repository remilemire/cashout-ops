import { type CashoutDocumentClassification } from "@/api/types";
import { fieldLabel } from "@/lib/format";

/**
 * Curated presentation of the extraction schemas: display order, grouping,
 * and human labels per schema name. Labels are presentation only — the
 * extracted JSON keys never change.
 */

// Curated over enumLabel(): brand casing ("TouchBistro") survives.
export const CLASSIFICATION_LABELS: Record<
  CashoutDocumentClassification,
  string
> = {
  touchbistro_report: "TouchBistro report",
  server_summary_report: "Server summary report",
  gift_certificate: "Gift certificate",
};

// Mirrors the backend extraction-schema registry: each classification's schema
// name, for looking up its curated field groups.
export const CLASSIFICATION_SCHEMA_NAMES: Record<
  CashoutDocumentClassification,
  string
> = {
  touchbistro_report: "TouchBistroReportData",
  server_summary_report: "ServerSummaryReportData",
  gift_certificate: "GiftCertificateData",
};

export interface FieldGroup {
  /** Null on the catch-all group when it is the only group. */
  heading: string | null;
  fields: { key: string; label: string }[];
}

const SCHEMA_FIELD_GROUPS: Record<
  string,
  { heading: string; fields: { key: string; label: string }[] }[]
> = {
  TouchBistroReportData: [
    {
      heading: "Sales",
      fields: [
        { key: "food_net_sales", label: "Food net sales" },
        { key: "drink_net_sales", label: "Drink net sales" },
        { key: "total_net_sales", label: "Total net sales" },
      ],
    },
    {
      heading: "Payments",
      fields: [
        { key: "cash_payment_total", label: "Cash payments" },
        { key: "card_payment_total", label: "Card payments" },
        { key: "card_transaction_count", label: "Card orders" },
        {
          key: "integrated_gift_card_payment_total",
          label: "Integrated gift card payments",
        },
        {
          key: "integrated_gift_card_transaction_count",
          label: "Integrated gift card orders",
        },
      ],
    },
    {
      heading: "Tips",
      fields: [{ key: "card_tip_total", label: "Card tips" }],
    },
  ],
  GiftCertificateData: [
    { heading: "Amount", fields: [{ key: "amount", label: "Amount" }] },
  ],
  ServerSummaryReportData: [
    {
      heading: "Totals",
      fields: [
        { key: "grand_total", label: "Grand total" },
        { key: "grand_total_transaction_count", label: "Orders" },
      ],
    },
  ],
};

/**
 * The full curated groups for a schema, independent of any data (empty for
 * unknown names). {@link groupFields} filters by data presence, which is
 * wrong for a blank form — manual entry renders every field.
 */
export function fieldGroupsFor(schemaName: string): FieldGroup[] {
  return (SCHEMA_FIELD_GROUPS[schemaName] ?? []).map((group) => ({
    heading: group.heading as string | null,
    fields: [...group.fields],
  }));
}

/**
 * Order the data's keys into the schema's curated groups, keeping only the
 * keys actually present. Keys the registry doesn't know — everything, when
 * the schema is null or unrecognized — land in a trailing catch-all group
 * labeled via the generic fieldLabel fallback ("Other" when curated groups
 * precede it; omit its heading when it is the only group).
 */
export function groupFields(
  schemaName: string | null | undefined,
  data: Record<string, unknown>,
): FieldGroup[] {
  const registry =
    (schemaName != null && SCHEMA_FIELD_GROUPS[schemaName]) || [];
  const known = new Set(
    registry.flatMap((group) => group.fields.map((field) => field.key)),
  );

  const groups: FieldGroup[] = registry
    .map((group) => ({
      heading: group.heading as string | null,
      fields: group.fields.filter((field) => field.key in data),
    }))
    .filter((group) => group.fields.length > 0);

  const unknown = Object.keys(data).filter((key) => !known.has(key));
  if (unknown.length > 0) {
    groups.push({
      heading: groups.length > 0 ? "Other" : null,
      fields: unknown.map((key) => ({ key, label: fieldLabel(key) })),
    });
  }
  return groups;
}

/**
 * Label for a single field key or issue path. A dotted path ("foo.bar")
 * matches the curated label of its first segment; unknown keys fall back to
 * the generic fieldLabel humanization of the full path.
 */
export function fieldLabelFor(
  schemaName: string | null | undefined,
  path: string,
): string {
  const key = path.split(".")[0] ?? path;
  const curated = (
    schemaName != null ? SCHEMA_FIELD_GROUPS[schemaName] : undefined
  )
    ?.flatMap((group) => group.fields)
    .find((field) => field.key === key);
  return curated?.label ?? fieldLabel(path);
}
