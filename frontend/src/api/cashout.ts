// frontend/src/api/cashout.ts

import { api } from "./client";
import type {
  CashoutDataRow,
  CashoutDocumentAnalysis,
  CashoutSubmission,
  CashoutSubmissionDetail,
  CashoutSubmissionListItem,
  CompleteSubmissionInput,
  CreateSubmissionInput,
  ManualDocumentInput,
  RetryAnalysisInput,
  UpdateSubmissionInput,
  VerifyAnalysisInput,
} from "./types";

export const cashoutApi = {
  listSubmissions: () =>
    api<CashoutSubmissionListItem[]>("/cashout/submissions"),
  createSubmission: (input?: CreateSubmissionInput) =>
    api<CashoutSubmission>("/cashout/submissions", {
      method: "POST",
      // A plain "for today" cashout sends no body at all.
      ...(input !== undefined && { json: input }),
    }),
  /** Move a processing cashout to another business day. */
  updateSubmission: (id: string, input: UpdateSubmissionInput) =>
    api<CashoutSubmission>(`/cashout/submissions/${id}`, {
      method: "PATCH",
      json: input,
    }),
  getSubmission: (id: string) =>
    api<CashoutSubmissionDetail>(`/cashout/submissions/${id}`),
  completeSubmission: (id: string, input: CompleteSubmissionInput) =>
    api<CashoutSubmission>(`/cashout/submissions/${id}/complete`, {
      method: "POST",
      json: input,
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
  /** Upload a document with manually entered details; no AI extraction runs. */
  uploadManualDocument: (
    submissionId: string,
    file: File,
    input: ManualDocumentInput,
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("payload", JSON.stringify(input));
    return api<CashoutDocumentAnalysis>(
      `/cashout/submissions/${submissionId}/documents/manual`,
      { method: "POST", body },
    );
  },
  /**
   * Start an upload over: discard every analysis and crop, find the documents
   * in it again, and extract each afresh. Returns the fresh first analysis.
   */
  restartDocument: (documentId: string) =>
    api<CashoutDocumentAnalysis>(`/cashout/documents/${documentId}/extract`, {
      method: "POST",
    }),
  /** Remove a document (and its analyses) from an incomplete submission. */
  deleteDocument: (documentId: string) =>
    api<void>(`/cashout/documents/${documentId}`, { method: "DELETE" }),
  /** Plain URL for viewing the original file (img src / link href). */
  documentContentUrl: (documentId: string) =>
    `/api/cashout/documents/${documentId}/content`,

  getAnalysis: (id: string) =>
    api<CashoutDocumentAnalysis>(`/cashout/analyses/${id}`),
  /** Plain URL for the crop the analysis read; 404 when it read the whole image. */
  analysisCroppedUrl: (id: string) => `/api/cashout/analyses/${id}/cropped`,
  /**
   * Re-run one analysis over the crop it read; a corrected classification
   * skips the AI classify step.
   */
  retryAnalysis: (id: string, input?: RetryAnalysisInput) =>
    api<CashoutDocumentAnalysis>(`/cashout/analyses/${id}/extract`, {
      method: "POST",
      // A bare retry sends no body at all.
      ...(input !== undefined && { json: input }),
    }),
  /** Replace a failed or unverified analysis with manually entered details. */
  enterManualAnalysis: (id: string, input: ManualDocumentInput) =>
    api<CashoutDocumentAnalysis>(`/cashout/analyses/${id}/manual`, {
      method: "POST",
      json: input,
    }),
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

  listData: () => api<CashoutDataRow[]>("/cashout/data"),
};

/** Central react-query keys so invalidation stays consistent. */
export const cashoutKeys = {
  submissions: ["cashout", "submissions"] as const,
  submission: (id: string) => ["cashout", "submission", id] as const,
  analysis: (id: string) => ["cashout", "analysis", id] as const,
  data: ["cashout", "data"] as const,
};
