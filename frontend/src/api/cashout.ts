// frontend/src/api/cashout.ts

import { api } from "./client";
import type {
  CashoutData,
  CashoutDocumentAnalysis,
  CashoutSubmission,
  CashoutSubmissionDetail,
  CashoutSubmissionListItem,
  VerifyAnalysisInput,
} from "./types";

export const cashoutApi = {
  listSubmissions: () =>
    api<CashoutSubmissionListItem[]>("/cashout/submissions"),
  createSubmission: () =>
    api<CashoutSubmission>("/cashout/submissions", { method: "POST" }),
  getSubmission: (id: string) =>
    api<CashoutSubmissionDetail>(`/cashout/submissions/${id}`),
  completeSubmission: (id: string) =>
    api<CashoutSubmission>(`/cashout/submissions/${id}/complete`, {
      method: "POST",
    }),
  /** Cancel an incomplete cashout: deletes it and its uploaded documents. */
  cancelSubmission: (id: string) =>
    api<void>(`/cashout/submissions/${id}`, { method: "DELETE" }),
  /** Admin only: reopen a completed cashout, removing its reconciled data. */
  unsubmitSubmission: (id: string) =>
    api<CashoutSubmission>(`/cashout/submissions/${id}/unsubmit`, {
      method: "POST",
    }),

  uploadDocument: (submissionId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return api<CashoutDocumentAnalysis>(
      `/cashout/submissions/${submissionId}/documents`,
      { method: "POST", body },
    );
  },
  extractDocument: (documentId: string) =>
    api<CashoutDocumentAnalysis>(`/cashout/documents/${documentId}/extract`, {
      method: "POST",
    }),
  /** Remove a document (and its analysis) from an incomplete submission. */
  deleteDocument: (documentId: string) =>
    api<void>(`/cashout/documents/${documentId}`, { method: "DELETE" }),
  /** Plain URL for viewing the original file (img src / link href). */
  documentContentUrl: (documentId: string) =>
    `/api/cashout/documents/${documentId}/content`,

  getAnalysis: (id: string) =>
    api<CashoutDocumentAnalysis>(`/cashout/analyses/${id}`),
  verifyAnalysis: (id: string, input: VerifyAnalysisInput) =>
    api<CashoutDocumentAnalysis>(`/cashout/analyses/${id}/verify`, {
      method: "POST",
      json: input,
    }),
  /** Send a verified analysis back to needs-verification for editing. */
  unverifyAnalysis: (id: string) =>
    api<CashoutDocumentAnalysis>(`/cashout/analyses/${id}/unverify`, {
      method: "POST",
    }),

  listData: () => api<CashoutData[]>("/cashout/data"),
};

/** Central react-query keys so invalidation stays consistent. */
export const cashoutKeys = {
  submissions: ["cashout", "submissions"] as const,
  submission: (id: string) => ["cashout", "submission", id] as const,
  analysis: (id: string) => ["cashout", "analysis", id] as const,
  data: ["cashout", "data"] as const,
};
