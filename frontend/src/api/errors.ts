import type { ErrorCode, ErrorContext, ValidationIssue } from "./types";

/** All application wording lives here; the backend sends codes and context. */
const ERROR_MESSAGES = {
  INTERNAL: "Something went wrong.",
  BAD_REQUEST: "The request could not be processed.",
  VALIDATION_FAILED: "There was a problem with the submission.",
  UNAUTHENTICATED: "Authentication required.",
  FORBIDDEN: "You do not have permission to perform this action.",
  ROUTE_NOT_FOUND: "The requested route does not exist.",
  CONFLICT: "The request conflicts with the current state.",
  RATE_LIMITED: "Too many attempts. Please wait a moment and try again.",
  SERVICE_UNAVAILABLE: "The service is temporarily unavailable.",
  EMAIL_CHALLENGE_INVALID: "That sign-in code is invalid or has expired.",
  INVALID_CSRF_TOKEN:
    "Your session security check failed. Refresh the page and try again.",
  OAUTH_SIGN_IN_FAILED:
    "That sign-in could not be completed. Please try again.",
  OAUTH_ISSUER_NOT_ENABLED: "That sign-in provider is not available.",
  INVALID_SESSION: "Invalid or expired session.",
  ANALYSIS_NOT_FOUND: "Analysis not found.",
  CROP_NOT_FOUND: "The cropped document is not available.",
  ANALYSIS_VERIFIED: "This analysis has already been verified.",
  ANALYSIS_NOT_VERIFIED: "Only a verified analysis can be edited.",
  EXTRACTION_IN_PROGRESS: "An extraction is already in progress.",
  EXTRACTION_FAILED: "The extraction failed; retry it before verifying.",
  RECONCILE_TOUCHBISTRO_MISSING:
    "Add the TouchBistro end-of-day report before completing.",
  RECONCILE_TOUCHBISTRO_DUPLICATE:
    "A cashout takes exactly one TouchBistro end-of-day report.",
  RECONCILE_CARD_PAYMENT_MISMATCH: (ctx: ErrorContext) => {
    const cardPayments = parameter(ctx, "cardPaymentTotal");
    const grandTotals = parameter(ctx, "serverSummaryTotal");
    if (cardPayments === undefined || grandTotals === undefined) {
      return "The TouchBistro card payments do not match the server summary grand totals. Re-check both before completing.";
    }
    // Present only when a deposit was taken off the card payments first.
    const deposit = parameter(ctx, "depositTotal");
    const reportSide =
      deposit === undefined
        ? `$${cardPayments}`
        : `$${cardPayments}, less a $${deposit} deposit`;
    return `The TouchBistro card payments (${reportSide}) do not match the server summary grand totals ($${grandTotals}). Re-check both before completing.`;
  },
  RECONCILE_CARD_TRANSACTION_MISMATCH:
    "The TouchBistro card orders do not match the server summary transaction counts. Re-check both before completing.",
  RECONCILE_GIFT_CARD_TRANSACTION_MISMATCH: (ctx: ErrorContext) => {
    const orders = parameter(ctx, "integratedGiftCardTransactionCount");
    const count = parameter(ctx, "giftCertificateCount");
    if (orders === undefined || count === undefined) {
      return "The TouchBistro integrated gift card orders do not match the number of gift certificates. Re-check both before completing.";
    }
    return `The TouchBistro integrated gift card orders (${orders}) do not match the number of gift certificates (${count}). Re-check both before completing.`;
  },
  RECONCILE_GIFT_CARD_PAYMENT_MISMATCH: (ctx: ErrorContext) => {
    const payments = parameter(ctx, "integratedGiftCardPaymentTotal");
    const total = parameter(ctx, "giftCertificateTotal");
    if (payments === undefined || total === undefined) {
      return "The TouchBistro integrated gift card payments do not match the gift certificate amounts. Re-check both before completing.";
    }
    return `The TouchBistro integrated gift card payments ($${payments}) do not match the gift certificate amounts ($${total}). Re-check both before completing.`;
  },
  RECONCILE_DOCUMENT_DATA_INVALID:
    "A document's verified details cannot be read. Re-verify it and try again.",
  UPLOAD_NOT_FOUND: "Upload not found.",
  UPLOAD_DUPLICATE: "This file has already been uploaded to this cashout.",
  UNSUPPORTED_UPLOAD_TYPE: "Unsupported file type.",
  SUBMISSION_NOT_FOUND: "Cashout submission not found.",
  SUBMISSION_COMPLETED: "This cashout has already been completed.",
  SUBMISSION_NOT_COMPLETED: "Only a completed cashout can be unsubmitted.",
  SUBMISSION_EMPTY: "Upload at least one document before completing.",
  SUBMISSION_UNVERIFIED: "Every document must be verified before completing.",
  SUBMISSION_HAS_DATA:
    "This cashout has reconciled data and cannot be deleted.",
  SUBMISSION_DUPLICATE_DAY: "A cashout for this day already exists.",
  USER_NOT_FOUND: "User not found.",
  EMAIL_TAKEN: "This email is already in use.",
  CANNOT_MODIFY_OWN_ADMIN: "You cannot change your own admin access.",
  CANNOT_MODIFY_OWNER: "The owner's role cannot be changed.",
  CANNOT_DELETE_OWNER: "The owner account cannot be deleted.",
  TRANSFER_TARGET_NOT_ADMIN: "Ownership can only be transferred to an admin.",
  OWNER_ALREADY_EXISTS: "There is already an owner.",
  UPLOAD_TOO_LARGE: (ctx: ErrorContext) =>
    parameter(ctx, "maxSizeMb") !== undefined
      ? `The file exceeds the ${parameter(ctx, "maxSizeMb")} MB size limit.`
      : "The file exceeds the size limit.",
} satisfies Record<ErrorCode, string | ((ctx: ErrorContext) => string)>;

export function errorMessage(code: ErrorCode, ctx: ErrorContext): string {
  // A newer backend may introduce a code this frontend does not know yet.
  if (!Object.hasOwn(ERROR_MESSAGES, code)) return ERROR_MESSAGES.INTERNAL;
  if (code === "RATE_LIMITED") {
    const seconds = parameter(ctx, "retryAfterSeconds");
    if (seconds !== undefined) {
      return `Too many attempts. Try again in ${seconds} seconds.`;
    }
  }
  const message = ERROR_MESSAGES[code];
  return typeof message === "function" ? message(ctx) : message;
}

/** Unknown or custom validators intentionally fall back to a generic message. */
export function validationMessage({ code, ctx }: ValidationIssue): string {
  switch (code) {
    case "missing":
      return "This field is required.";
    case "extra_forbidden":
      return "This field isn't allowed.";
    case "bool_type":
    case "bool_parsing":
      return "Enter true or false.";
    case "string_type":
    case "string_unicode":
      return "Enter valid text.";
    case "int_type":
    case "int_parsing":
    case "int_from_float":
      return "Enter a whole number.";
    case "float_type":
    case "float_parsing":
    case "decimal_type":
    case "decimal_parsing":
    case "finite_number":
      return "Enter a valid number.";
    case "dict_type":
    case "list_type":
    case "tuple_type":
    case "set_type":
    case "model_type":
    case "model_attributes_type":
      return "Enter a valid object or list.";
    case "greater_than":
      return constraint(
        ctx,
        "gt",
        (n) => `Must be greater than ${n}.`,
        "Too small.",
      );
    case "greater_than_equal":
      return constraint(
        ctx,
        "ge",
        (n) => `Must be at least ${n}.`,
        "Too small.",
      );
    case "less_than":
      return constraint(
        ctx,
        "lt",
        (n) => `Must be less than ${n}.`,
        "Too big.",
      );
    case "less_than_equal":
      return constraint(ctx, "le", (n) => `Must be at most ${n}.`, "Too big.");
    case "string_too_short":
      return constraint(
        ctx,
        "minLength",
        (n) => `Minimum ${n} characters required.`,
        "Too short.",
      );
    case "string_too_long":
      return constraint(
        ctx,
        "maxLength",
        (n) => `Maximum ${n} characters allowed.`,
        "Too long.",
      );
    case "too_short":
      return constraint(
        ctx,
        "minLength",
        (n) => `At least ${n} items required.`,
        "Too few items.",
      );
    case "too_long":
      return constraint(
        ctx,
        "maxLength",
        (n) => `At most ${n} items allowed.`,
        "Too many items.",
      );
    case "enum":
    case "literal_error":
      return constraint(
        ctx,
        "expected",
        (options) => `Choose from: ${options}.`,
        "Choose one of the allowed values.",
      );
    case "multiple_of":
      return constraint(
        ctx,
        "multipleOf",
        (n) => `Must be a multiple of ${n}.`,
        "Enter a valid multiple.",
      );
    case "decimal_max_digits":
      return constraint(
        ctx,
        "maxDigits",
        (n) => `Use at most ${n} digits.`,
        "Too many digits.",
      );
    case "decimal_max_places":
      return constraint(
        ctx,
        "decimalPlaces",
        (n) => `Use at most ${n} decimal places.`,
        "Too many decimal places.",
      );
    case "decimal_whole_digits":
      return constraint(
        ctx,
        "wholeDigits",
        (n) => `Use at most ${n} digits before the decimal point.`,
        "Too many digits before the decimal point.",
      );
    default:
      return "Invalid value.";
  }
}

function parameter(
  ctx: ErrorContext,
  key: string,
): string | number | undefined {
  const value = ctx[key];
  return typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value))
    ? value
    : undefined;
}

function constraint(
  ctx: ErrorContext,
  key: string,
  format: (value: string | number) => string,
  fallback: string,
): string {
  const value = parameter(ctx, key);
  return value === undefined ? fallback : format(value);
}
