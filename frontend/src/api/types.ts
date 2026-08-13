// frontend/src/api/types.ts

/** Contracts mirroring the backend's `BaseOut` schemas (camelCase JSON). */

// ---------- Errors (app/errors) ----------

export type ErrorKind =
  | "BAD_REQUEST"
  | "NOT_FOUND"
  | "CONFLICT"
  | "VALIDATION"
  | "FORBIDDEN"
  | "UNAUTHORIZED"
  | "TOO_MANY_REQUESTS"
  | "INTERNAL"
  | "SERVICE_UNAVAILABLE";

/** Base codes plus each feature's codes (see the backend errors.py modules). */
export type ErrorCode =
  | "INTERNAL"
  | "BAD_REQUEST"
  | "VALIDATION_FAILED"
  | "UNAUTHENTICATED"
  | "FORBIDDEN"
  | "ROUTE_NOT_FOUND"
  | "CONFLICT"
  | "RATE_LIMITED"
  | "SERVICE_UNAVAILABLE"
  // users
  | "USER_NOT_FOUND"
  | "EMAIL_TAKEN"
  | "CANNOT_MODIFY_OWNER"
  | "CANNOT_DELETE_OWNER"
  | "TRANSFER_TARGET_NOT_ADMIN"
  // auth
  | "EMAIL_CHALLENGE_INVALID"
  | "INVALID_SESSION"
  | "INVALID_CSRF_TOKEN"
  | "OAUTH_FLOW_INVALID"
  | "OAUTH_ACCOUNT_NOT_FOUND"
  | "OAUTH_ISSUER_NOT_ENABLED"
  // cashout
  | "SUBMISSION_NOT_FOUND"
  | "DOCUMENT_NOT_FOUND"
  | "ANALYSIS_NOT_FOUND"
  | "SUBMISSION_COMPLETED"
  | "SUBMISSION_EMPTY"
  | "SUBMISSION_UNVERIFIED"
  | "SUBMISSION_HAS_DATA"
  | "ANALYSIS_VERIFIED"
  | "EXTRACTION_IN_PROGRESS"
  | "EXTRACTION_FAILED"
  | "DOCUMENT_TOO_LARGE"
  | "DOCUMENT_DUPLICATE"
  | "UNSUPPORTED_DOCUMENT_TYPE";

export interface ValidationIssue {
  code: string;
  path: (string | number)[];
  message: string;
}

export interface ErrorResponse {
  kind: ErrorKind;
  code: ErrorCode;
  message: string;
  /** Per-field details; present only when `kind` is "VALIDATION". */
  issues?: ValidationIssue[];
}

// ---------- Users / auth ----------

export type UserRole = "staff" | "admin" | "owner";

/** Owners are admins-plus: every admin capability applies to owners too. */
export function isAdminRole(role: UserRole): boolean {
  return role === "admin" || role === "owner";
}

export interface User {
  id: string;
  createdAt: string;
  email: string;
  fullName: string;
  role: UserRole;
}

export interface UserCreateInput {
  email: string;
  fullName: string;
}

export interface UserUpdateInput {
  fullName: string;
}

export interface LoginStartInput {
  email: string;
}

/** Handle for an in-progress passwordless login challenge. */
export interface LoginStart {
  challengeId: string;
}

export interface VerifyLoginLinkInput {
  challengeId: string;
  token: string;
}

/** The 6-digit code shown on the magic-link page. */
export interface LoginCode {
  code: string;
}

export interface VerifyLoginCodeInput {
  challengeId: string;
  code: string;
}

// ---------- Cashout ----------

export type CashoutSubmissionStatus = "PROCESSING" | "COMPLETED";

export type DocumentAnalysisStatus =
  | "EXTRACTING"
  | "NEEDS_VERIFICATION"
  | "VERIFIED"
  | "FAILED";

export type CashoutDocumentClassification =
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
  classification: CashoutDocumentClassification | null;
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
