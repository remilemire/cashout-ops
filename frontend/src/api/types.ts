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
  | "CANNOT_MODIFY_OWN_ADMIN"
  | "CANNOT_MODIFY_OWNER"
  | "CANNOT_DELETE_OWNER"
  | "TRANSFER_TARGET_NOT_ADMIN"
  | "OWNER_ALREADY_EXISTS"
  // auth
  | "EMAIL_CHALLENGE_INVALID"
  | "INVALID_SESSION"
  | "INVALID_CSRF_TOKEN"
  | "OAUTH_SIGN_IN_FAILED"
  | "OAUTH_ISSUER_NOT_ENABLED"
  // cashout
  | "SUBMISSION_NOT_FOUND"
  | "UPLOAD_NOT_FOUND"
  | "ANALYSIS_NOT_FOUND"
  | "CROP_NOT_FOUND"
  | "SUBMISSION_COMPLETED"
  | "SUBMISSION_NOT_COMPLETED"
  | "SUBMISSION_EMPTY"
  | "SUBMISSION_UNVERIFIED"
  | "SUBMISSION_HAS_DATA"
  | "SUBMISSION_DUPLICATE_DAY"
  | "ANALYSIS_VERIFIED"
  | "ANALYSIS_NOT_VERIFIED"
  | "EXTRACTION_IN_PROGRESS"
  | "EXTRACTION_FAILED"
  | "UPLOAD_TOO_LARGE"
  | "UPLOAD_DUPLICATE"
  | "UNSUPPORTED_UPLOAD_TYPE"
  // cashout — reconciliation, raised while completing
  | "RECONCILE_TOUCHBISTRO_MISSING"
  | "RECONCILE_TOUCHBISTRO_DUPLICATE"
  | "RECONCILE_CARD_PAYMENT_MISMATCH"
  | "RECONCILE_CARD_TRANSACTION_MISMATCH"
  | "RECONCILE_GIFT_CARD_TRANSACTION_MISMATCH"
  | "RECONCILE_GIFT_CARD_PAYMENT_MISMATCH"
  | "RECONCILE_DOCUMENT_DATA_INVALID";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

/** Public message parameters. Keys use camelCase throughout the API. */
export type ErrorContext = Record<string, JsonValue>;

export interface ValidationIssue {
  /** Pydantic error type, e.g. `missing` or `greater_than_equal`. */
  code: string;
  path: (string | number)[];
  ctx: ErrorContext;
}

export interface ErrorResponse {
  kind: ErrorKind;
  code: ErrorCode;
  ctx: ErrorContext;
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
  | "server_summary_report"
  | "gift_certificate";

export const CASHOUT_DOCUMENT_CLASSIFICATIONS: CashoutDocumentClassification[] =
  ["touchbistro_report", "server_summary_report", "gift_certificate"];

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
  /** The day the cashout is for (YYYY-MM-DD); submittedAt is when it was opened. */
  businessDate: string;
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
  /**
   * Reading order among the upload's analyses (1-based): the order the
   * documents were found in it, page by page for a PDF.
   */
  position: number;
  /** Null when the details were entered manually (no AI ran). */
  provider: string | null;
  model: string | null;
  status: DocumentAnalysisStatus;
  classification: CashoutDocumentClassification | null;
  classificationConfidence: number | null;
  schemaName: string | null;
  /**
   * Which shape of the named schema the extracted data follows. Data written
   * under an older version keeps its shape until a re-extraction replaces it;
   * rendering stays data-driven, so no branching on it is needed here.
   */
  schemaVersion: number | null;
  /**
   * Set when the extraction read a crop — this analysis's document among
   * those found in the upload — rather than the whole upload: the crop is
   * served by `analysisCroppedUrl`, and is what to check the extraction
   * against. Null for an upload with no detectable text, cropping switched
   * off, or an analysis not yet extracted.
   */
  croppedContentType: DocumentContentType | null;
  extractedDataJson: Record<string, unknown> | null;
  extractionConfidence: number | null;
  issues: FieldIssue[] | null;
  errorCode: string | null;
  errorMessage: string | null;
  completedAt: string | null;
  verifiedDataJson: Record<string, unknown> | null;
  verifiedByUserId: string | null;
  verifiedAt: string | null;
  cashoutUploadId: string;
}

/**
 * The file a cashier submits to a cashout — a photo or PDF holding one or
 * more printed documents, each of which gets an analysis of its own.
 */
export interface CashoutUpload {
  id: string;
  createdAt: string;
  contentType: DocumentContentType;
  originalFilename: string;
  checksumSha256: string;
  uploadedByUserId: string;
  uploadedAt: string;
  cashoutSubmissionId: string;
  /**
   * One per document found in the upload (several receipts in one photo,
   * each page of a PDF), in reading order. Empty only for the instant
   * between the upload and its first analysis.
   */
  analyses: CashoutDocumentAnalysis[];
}

export type TipoutDepartment = "bar" | "kitchen" | "expo" | "host" | "manager";

/**
 * The departments a cashier can tip out to. The manager is not among them:
 * the server adds the manager to every completion, so there is no checkbox.
 */
export const SELECTABLE_TIPOUT_DEPARTMENTS: TipoutDepartment[] = [
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
   * Reconciled off the verified analyses — taken from the cashout's one
   * TouchBistro report. Always present: a cashout that cannot be reconciled
   * never completes, so no row exists without them.
   */
  foodNetSales: string;
  drinkNetSales: string;
  totalNetSales: string;
  cardPaymentTotal: string;
  cashPaymentTotal: string;
  cardTipTotal: string;

  /**
   * An admin's adjustment at completion: a deposit the TouchBistro report
   * counts among its card payments but no server summary shows, taken off
   * `cardPaymentTotal` for the cross-check only — that figure stays the
   * report's. Both null when no adjustment was recorded.
   */
  depositTotal: string | null;
  adjustmentNote: string | null;

  /**
   * Which departments this cashout tipped out to (the cashier's selection
   * plus the manager, who is on every cashout), and the rates it closed
   * against. The rates are the row's own snapshot, so a later rate change
   * never restates a cashout that has already closed.
   */
  tipoutDepartments: TipoutDepartment[];
  barTipoutRate: string;
  kitchenTipoutRate: string;
  expoTipoutRate: string;
  hostTipoutRate: string;
  managerTipoutRate: string;

  /** Null for a department that was not tipped out. */
  barTipout: string | null;
  kitchenTipout: string | null;
  expoTipout: string | null;
  hostTipout: string | null;
  managerTipout: string | null;

  /**
   * At most one side is set: whichever way the cash/card-tip balance falls
   * after adding the tipouts (neither, on the exact tie).
   */
  cashOwedToHouse: string | null;
  cashOwedToEmployee: string | null;

  submissionId: string;
}

/**
 * The list endpoint's shape: a data row with its submission's identity — who
 * the cashout was for and its day. The copy embedded in a submission detail
 * has no nested submission (it already sits inside one).
 */
export interface CashoutDataRow extends CashoutData {
  submission: {
    id: string;
    /** The day the cashout is for (YYYY-MM-DD). */
    businessDate: string;
    employee: User;
  };
}

export interface CashoutSubmissionDetail extends CashoutSubmission {
  employee: User;
  uploads: CashoutUpload[];
  data: CashoutData | null;
}

export interface CreateSubmissionInput {
  /** The day the cashout is for (YYYY-MM-DD); omit for today. */
  businessDate?: string;
}

export interface UpdateSubmissionInput {
  /** The day the cashout is for (YYYY-MM-DD). */
  businessDate: string;
}

/**
 * Admin only. A deposit the TouchBistro report counts among its card payments
 * but no server summary shows: subtracted from the report's card payments
 * before the cross-check, and recorded on the resulting data.
 */
export interface CashoutAdjustmentInput {
  /** Decimal string, e.g. "234.56". */
  depositTotal: string;
  /** Omitted when empty. */
  note?: string;
}

export interface CompleteSubmissionInput {
  /**
   * The cashier's selection; the rest are left untipped. The server adds the
   * manager to every completion, so naming it is allowed but never needed.
   */
  tipoutDepartments: TipoutDepartment[];
  /** Admin only: a non-admin sending one is refused outright. */
  adjustment?: CashoutAdjustmentInput;
}

export interface VerifyAnalysisInput {
  /** Corrections to the extracted data; omit to confirm as-is. */
  verifiedData?: Record<string, unknown>;
}

export interface RetryExtractionInput {
  /**
   * Corrected classification: the rerun skips AI classification and extracts
   * as this type (its confidence is recorded as null). Omit for a plain
   * retry — the full classify + extract pipeline.
   */
  classification?: CashoutDocumentClassification;
}

export interface ManualEntryInput {
  classification: CashoutDocumentClassification;
  /** snake_case schema keys; raw string values — the backend coerces. */
  data: Record<string, string>;
}
