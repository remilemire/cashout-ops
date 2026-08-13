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
  classification: "manual_note",
  classificationConfidence: 0.95,
  schemaName: "ManualNoteData",
  extractedDataJson: { note: "cash $100", total: 12.5 },
  extractionConfidence: 0.7,
  issues: [{ path: "note", message: "partially legible" }],
  errorCode: null,
  errorMessage: null,
  completedAt: "2026-07-17T00:01:00Z",
  verifiedDataJson: null,
  verifiedByUserId: null,
  verifiedAt: null,
  cashoutDocumentId: "document-1",
};

function renderForm(editable = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(
    <VerificationForm
      analysis={analysis}
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

    fireEvent.change(screen.getByLabelText("Total"), {
      target: { value: "13" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /verify with 1 correction/i }),
    );

    await waitFor(() =>
      expect(verifyMock).toHaveBeenCalledWith("analysis-1", {
        verifiedData: { note: "cash $100", total: 13 },
      }),
    );
  });

  it("renders read-only for non-owners", () => {
    renderForm(false);

    expect(screen.queryByRole("button", { name: /verify/i })).toBeNull();
    expect(screen.getByText("cash $100")).toBeDefined();
  });
});
