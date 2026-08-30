// frontend/src/features/cashout/ManualDocumentDialog.test.tsx

import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";

import { ManualDocumentDialog } from "./ManualDocumentDialog";

vi.mock("@/components/dialog", () => ({
  Dialog: ({
    open,
    title,
    children,
  }: {
    open: boolean;
    title: string;
    children: ReactNode;
  }) =>
    open ? (
      <div role="dialog" aria-label={title}>
        <h2>{title}</h2>
        {children}
      </div>
    ) : null,
}));

const TOUCHBISTRO_LABELS = [
  "Food net sales",
  "Drink net sales",
  "Total net sales",
  "Cash payments",
  "Card payments",
  "Card orders",
  "Card tips",
];

function renderDialog(
  overrides: Partial<Parameters<typeof ManualDocumentDialog>[0]> = {},
) {
  const onSubmit = vi.fn();
  const utils = render(
    <ManualDocumentDialog
      open
      onClose={vi.fn()}
      withFile={false}
      pending={false}
      error={null}
      onSubmit={onSubmit}
      {...overrides}
    />,
  );
  return { onSubmit, ...utils };
}

describe("ManualDocumentDialog", () => {
  it("offers every document type", () => {
    renderDialog();

    expect(
      screen.getByRole("option", { name: "TouchBistro report" }),
    ).toBeDefined();
    expect(
      screen.getByRole("option", { name: "Server summary report" }),
    ).toBeDefined();
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("swaps the field set when the classification changes", () => {
    renderDialog();

    // TouchBistro (the default) renders all seven fields under headings.
    for (const label of TOUCHBISTRO_LABELS) {
      expect(screen.getByLabelText(label)).toBeDefined();
    }
    expect(screen.getByText("Sales")).toBeDefined();
    expect(screen.getByText("Payments")).toBeDefined();
    expect(screen.getByText("Tips")).toBeDefined();

    fireEvent.change(screen.getByLabelText("Document type"), {
      target: { value: "server_summary_report" },
    });

    expect(screen.getByLabelText("Grand total")).toBeDefined();
    expect(screen.getByLabelText("Orders")).toBeDefined();
    expect(screen.queryByLabelText("Food net sales")).toBeNull();
    // A single group renders without its heading.
    expect(screen.queryByText("Totals")).toBeNull();
  });

  it("submits every schema key as a raw string plus the chosen file", () => {
    const { onSubmit, container } = renderDialog({ withFile: true });

    const file = new File(["img"], "report.jpg", { type: "image/jpeg" });
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });
    fireEvent.change(screen.getByLabelText("Food net sales"), {
      target: { value: "1,000.00" },
    });
    fireEvent.change(screen.getByLabelText("Card orders"), {
      target: { value: "42" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add details" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith(
      {
        classification: "touchbistro_report",
        data: {
          food_net_sales: "1,000.00",
          drink_net_sales: "",
          total_net_sales: "",
          cash_payment_total: "",
          card_payment_total: "",
          card_transaction_count: "42",
          card_tip_total: "",
        },
      },
      file,
    );
  });

  it("shows a backend validation message on its field", () => {
    renderDialog({
      initialClassification: "server_summary_report",
      error: new ApiError(422, {
        kind: "VALIDATION",
        code: "VALIDATION_FAILED",
        message: "Validation failed.",
        // The backend camelCases issue paths: grand_total → grandTotal.
        issues: [
          {
            code: "DECIMAL_TYPE",
            path: ["grandTotal"],
            message: "Enter a valid number.",
          },
        ],
      }),
    });

    expect(screen.getByText("Enter a valid number.")).toBeDefined();
    // Every issue landed on a field, so no general banner repeats it.
    expect(screen.queryByText("Validation failed.")).toBeNull();
  });

  it("banners an error that maps to no field", () => {
    renderDialog({
      error: new ApiError(409, {
        kind: "CONFLICT",
        code: "ANALYSIS_VERIFIED",
        message: "This document is already verified.",
      }),
    });

    expect(
      screen.getByText("This document is already verified."),
    ).toBeDefined();
  });

  it("disables submit until a file is chosen when one is required", () => {
    const { container } = renderDialog({ withFile: true });

    const submit = screen.getByRole("button", {
      name: "Add details",
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);

    const file = new File(["img"], "report.jpg", { type: "image/jpeg" });
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });

    expect(submit.disabled).toBe(false);
    // The chosen filename replaces the picker label.
    expect(screen.getByRole("button", { name: /report\.jpg/ })).toBeDefined();
  });
});
