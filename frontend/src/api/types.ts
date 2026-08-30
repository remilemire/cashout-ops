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
  | "OAUTH_SIGN_IN_FAILED"
  | "OAUTH_ISSUER_NOT_ENABLED"
  // cashout
  | "SUBMISSION_NOT_FOUND"
  | "DOCUMENT_NOT_FOUND"
  | "ANALYSIS_NOT_FOUND"
  | "SUBMISSION_COMPLETED"
  | "SUBMISSION_NOT_COMPLETED"
  | "SUBMISSION_EMPTY"
  | "SUBMISSION_UNVERIFIED"
  | "SUBMISSION_HAS_DATA"
  | "ANALYSIS_VERIFIED"
  | "ANALYSIS_NOT_VERIFIED"
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

export type CashoutSubmissionStatus = "processing" | "completed";

export type DocumentAnalysisStatus =
  | "extracting"
  | "needs_verification"
  | "verified"
  | "failed";

/** Every classification is extractable: a document the AI cannot place is a
 * failed analysis (errorCode "unclassifiable_document"), not a classification. */
export type CashoutDocumentClassification =
  | "touchbistro_report"
  | "server_summary_report";

export const CASHOUT_DOCUMENT_CLASSIFICATIONS: CashoutDocumentClassification[] =
  ["touchbistro_report", "server_summary_report"];

export type DocumentContentType =
  | "image/jpeg"
  | "image/png"
  | "image/webp"
  | "application/pdf";

export const DOCUMENT_CONTENT_TYPES: DocumentContentType[] = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
];

export interface CashoutSubmission {
  id: string;
  createdAt: string;
  status: CashoutSubmissionStatus;
  employeeUserId: string;
  submittedAt: string;
  /** Who performed the most recent completion (an admin may act for the employee). */
  completedByUserId: string | null;
  /** When it was completed first; set once and never overwritten. */
  firstCompletedAt: string | null;
  /**
   * The departments chosen at the most recent completion — kept through
   * unsubmit so re-completion starts from the previous choice (unlike
   * CashoutData.tipoutDepartments, which the unsubmit drops with its row).
   * Null means never completed.
   */
  tipoutDepartments: TipoutDepartment[] | null;
  updatedAt: string;
}

export interface CashoutSubmissionListItem extends CashoutSubmission {
  employee: User;
}

export interface FieldIssue {
  path: string;
  message: string;
}

export interface CashoutDocumentAnalysis {
  id: string;
  createdAt: string;
  /** Null when the details were entered manually (no AI ran). */
  provider: string | null;
  model: string | null;
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

export type TipoutDepartment = "bar" | "kitchen" | "expo" | "host";

export const TIPOUT_DEPARTMENTS: TipoutDepartment[] = [
  "bar",
  "kitchen",
  "expo",
  "host",
];

/** The reconciled result of a completed cashout. Amounts are decimal strings. */
export interface CashoutData {
  id: string;
  createdAt: string;

  /**
   * Reconciled off the verified analyses — null on a cashout completed before
   * reconciliation was implemented, which leaves the tipouts below null too.
   */
  foodNetSales: string | null;
  drinkNetSales: string | null;
  totalNetSales: string | null;
  cardPaymentTotal: string | null;
  cashPaymentTotal: string | null;
  cardTipTotal: string | null;

  /**
   * Which departments this cashout tipped out to, and the rates it closed
   * against. The rates are the row's own snapshot, so a later rate change
   * never restates a cashout that has already closed.
   */
  tipoutDepartments: TipoutDepartment[];
  barTipoutRate: string;
  kitchenTipoutRate: string;
  expoTipoutRate: string;
  hostTipoutRate: string;

  /** Null for a department that was not tipped out. */
  barTipout: string | null;
  kitchenTipout: string | null;
  expoTipout: string | null;
  hostTipout: string | null;

  /** At most one side is set: whichever way the cash/card-tip balance fell. */
  cashOwedToHouse: string | null;
  cashOwedToEmployee: string | null;

  submissionId: string;
}

export interface CashoutSubmissionDetail extends CashoutSubmission {
  employee: User;
  documents: CashoutDocument[];
  data: CashoutData | null;
}

export interface CompleteSubmissionInput {
  /** The departments this cashout tips out to; the rest are left untipped. */
  tipoutDepartments: TipoutDepartment[];
}

export interface VerifyAnalysisInput {
  /** Corrections to the extracted data; omit to confirm as-is. */
  verifiedData?: Record<string, unknown>;
}

export interface ExtractDocumentInput {
  /**
   * Corrected classification: the rerun skips AI classification and extracts
   * as this type (its confidence is recorded as null). Omit for a plain
   * retry — the full classify + extract pipeline.
   */
  classification?: CashoutDocumentClassification;
}

export interface ManualDocumentInput {
  classification: CashoutDocumentClassification;
  /** snake_case schema keys; raw string values — the backend coerces. */
  data: Record<string, string>;
}
