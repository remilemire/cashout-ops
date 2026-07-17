// frontend/src/api/types.ts

/** Contracts mirroring the backend's `BaseOut` schemas (camelCase JSON). */

// ---------- Errors (app/errors) ----------

export type ErrorCode =
  | "SERVER_ERROR"
  | "BAD_REQUEST"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "UNPROCESSABLE"
  | "IN_USE"
  | "ALREADY_EXISTS"
  | "INVALID_STATE";

export interface ErrorDetail {
  rule: string;
  detail: string;
  path: (string | number)[];
}

export interface ErrorBody {
  error: string;
  code: ErrorCode;
  message: string;
  errors?: ErrorDetail[];
}

// ---------- Users / auth ----------

export type UserRole = "CASHIER" | "ADMIN";

export interface User {
  id: string;
  createdAt: string;
  email: string;
  firstName: string;
  lastName: string;
  role: UserRole;
  isActive: boolean;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterInput extends LoginInput {
  firstName: string;
  lastName: string;
}

// ---------- Cashout ----------

export type CashoutSubmissionStatus = "PROCESSING" | "COMPLETED";

export type DocumentAnalysisStatus =
  | "EXTRACTING"
  | "NEEDS_VERIFICATION"
  | "VERIFIED"
  | "FAILED";

export type CashoutDocumentType =
  | "TOUCHBISTRO_SERVER_SHIFT_REPORT"
  | "PAYSTONE_TERMINAL_REPORT"
  | "PAYMENT_RECEIPT"
  | "DAILY_TIP_OUT_SHEET"
  | "DAILY_CASH_SUMMARY"
  | "MANUAL_NOTE"
  | "UNKNOWN";

export type DocumentContentType =
  | "image/jpeg"
  | "image/png"
  | "image/webp"
  | "application/pdf";

export interface CashoutSubmission {
  id: string;
  createdAt: string;
  status: CashoutSubmissionStatus;
  submittedByUserId: string;
  submittedAt: string;
}

export interface CashoutSubmissionListItem extends CashoutSubmission {
  submittedBy: User;
}

export interface FieldIssue {
  path: string;
  message: string;
}

export interface CashoutDocumentAnalysis {
  id: string;
  createdAt: string;
  provider: string;
  model: string;
  status: DocumentAnalysisStatus;
  classification: CashoutDocumentType | null;
  classificationConfidence: number | null;
  schemaName: string | null;
  extractedDataJson: Record<string, unknown> | null;
  extractionConfidence: number | null;
  issues: FieldIssue[] | null;
  errorCode: string | null;
  errorMessage: string | null;
  completedAt: string | null;
  verifiedDataJson: Record<string, unknown> | null;
  verifiedByUserId: string | null;
  verifiedAt: string | null;
  cashoutDocumentId: string;
}

export interface CashoutDocument {
  id: string;
  createdAt: string;
  documentType: CashoutDocumentType;
  contentType: DocumentContentType;
  originalFilename: string;
  checksumSha256: string;
  uploadedByUserId: string;
  uploadedAt: string;
  cashoutSubmissionId: string;
  analysis: CashoutDocumentAnalysis | null;
}

/** Reconciled totals; placeholder fields until the extraction schemas are real. */
export interface CashoutData {
  id: string;
  createdAt: string;
  dailyTipout: string | null;
  netTotal: string | null;
  cashTotal: string | null;
  cardTotal: string | null;
  submissionId: string;
}

export interface CashoutSubmissionDetail extends CashoutSubmission {
  submittedBy: User;
  documents: CashoutDocument[];
  data: CashoutData | null;
}

export interface VerifyAnalysisInput {
  /** Corrections to the extracted data; omit to confirm as-is. */
  verifiedData?: Record<string, unknown>;
}
