// frontend/src/features/cashout/VerificationForm.test.tsx

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cashoutApi } from "@/api/cashout";
import type { CashoutDocumentAnalysis } from "@/api/types";

import { VerificationForm } from "./VerificationForm";

vi.mock("@/api/cashout", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/cashout")>();
  return {
    ...actual,
    cashoutApi: { ...actual.cashoutApi, verifyAnalysis: vi.fn() },
  };
});

const verifyMock = vi.mocked(cashoutApi.verifyAnalysis);

const analysis: CashoutDocumentAnalysis = {
  id: "analysis-1",
  createdAt: "2026-07-17T00:00:00Z",
  provider: "anthropic",
  model: "test-model",
  status: "needs_verification",
  classification: "server_summary_report",
  classificationConfidence: 0.95,
  schemaName: "ServerSummaryReportData",
  // grand_total is a Decimal, so the API serializes it as a string; the count
  // stays a JSON number. Both types are exercised by the coercion test below.
  extractedDataJson: {
    grand_total: "1234.56",
    grand_total_transaction_count: 42,
  },
  extractionConfidence: 0.7,
  issues: [{ path: "grand_total", message: "partially legible" }],
  errorCode: null,
  errorMessage: null,
  completedAt: "2026-07-17T00:01:00Z",
  verifiedDataJson: null,
  verifiedByUserId: null,
  verifiedAt: null,
  cashoutDocumentId: "document-1",
};

function renderForm(
  editable = true,
  override: CashoutDocumentAnalysis = analysis,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(
    <VerificationForm
      analysis={override}
      submissionId="submission-1"
      editable={editable}
    />,
    { wrapper },
  );
}

beforeEach(() => {
  verifyMock.mockReset();
  verifyMock.mockResolvedValue({ ...analysis, status: "verified" });
});

describe("VerificationForm", () => {
  it("shows confidences and flags the issue on its field", () => {
    renderForm();

    expect(screen.getByText("95%")).toBeDefined();
    expect(screen.getByText("70%")).toBeDefined();
    expect(screen.getByText("partially legible")).toBeDefined();
  });

  it("verifies as-is without corrections", async () => {
    renderForm();

    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));

    await waitFor(() =>
      expect(verifyMock).toHaveBeenCalledWith("analysis-1", {}),
    );
  });

  it("sends type-coerced corrections when a field was edited", async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText("Orders"), {
      target: { value: "41" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /verify with 1 correction/i }),
    );

    await waitFor(() =>
      expect(verifyMock).toHaveBeenCalledWith("analysis-1", {
        verifiedData: {
          grand_total: "1234.56",
          grand_total_transaction_count: 41,
        },
      }),
    );
  });

  it("renders read-only for non-owners", () => {
    renderForm(false);

    expect(screen.queryByRole("button", { name: /verify/i })).toBeNull();
    expect(screen.getByText("1234.56")).toBeDefined();
  });

  it("labels fields from the schema registry without group headings for a single group", () => {
    renderForm();

    expect(screen.getByLabelText("Grand total")).toBeDefined();
    expect(screen.getByLabelText("Orders")).toBeDefined();
    // The awkward auto-humanized key label is gone.
    expect(screen.queryByText("Grand total transaction count")).toBeNull();
    // ServerSummary is a single "Totals" group, so it stays a flat list.
    expect(screen.queryByText("Totals")).toBeNull();
  });

  it("groups TouchBistro fields under headings in curated order", () => {
    renderForm(true, {
      ...analysis,
      classification: "touchbistro_report",
      schemaName: "TouchBistroReportData",
      extractedDataJson: {
        card_tip_total: "80.00",
        total_net_sales: "1500.00",
        cash_payment_total: "200.00",
        food_net_sales: "1000.00",
        card_transaction_count: 42,
        drink_net_sales: "500.00",
        card_payment_total: "1300.00",
      },
      issues: null,
    });

    expect(screen.getByText("Sales")).toBeDefined();
    expect(screen.getByText("Payments")).toBeDefined();
    expect(screen.getByText("Tips")).toBeDefined();

    const labels = screen
      .getAllByRole("textbox")
      .map((input) => input.getAttribute("aria-label"));
    expect(labels).toEqual([
      "Food net sales",
      "Drink net sales",
      "Total net sales",
      "Cash payments",
      "Card payments",
      "Card orders",
      "Card tips",
    ]);
  });

  it("renders unknown keys through the humanized fallback", () => {
    renderForm(true, {
      ...analysis,
      extractedDataJson: {
        ...analysis.extractedDataJson,
        mystery_field: "??",
      },
    });

    expect(screen.getByText("Other")).toBeDefined();
    expect(screen.getByLabelText("Mystery field")).toBeDefined();
  });
});
