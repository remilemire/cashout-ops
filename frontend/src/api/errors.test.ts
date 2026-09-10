import { describe, expect, it } from "vitest";

import { errorMessage, validationMessage } from "./errors";
import type { ErrorCode, ErrorContext } from "./types";

describe("error messages", () => {
  it("uses context for upload limits and retry timing", () => {
    expect(errorMessage("UPLOAD_TOO_LARGE", { maxSizeMb: 7 })).toBe(
      "The file exceeds the 7 MB size limit.",
    );
    expect(errorMessage("RATE_LIMITED", { retryAfterSeconds: 120 })).toBe(
      "Too many attempts. Try again in 120 seconds.",
    );
  });

  it("names both sides of a card payment mismatch, and any deposit taken off", () => {
    expect(
      errorMessage("RECONCILE_CARD_PAYMENT_MISMATCH", {
        cardPaymentTotal: "1234.56",
        serverSummaryTotal: "1000.00",
      }),
    ).toBe(
      "The TouchBistro card payments ($1234.56) do not match the server summary grand totals ($1000.00). Re-check both before completing.",
    );
    expect(
      errorMessage("RECONCILE_CARD_PAYMENT_MISMATCH", {
        cardPaymentTotal: "1234.56",
        serverSummaryTotal: "1000.00",
        depositTotal: "200.00",
      }),
    ).toBe(
      "The TouchBistro card payments ($1234.56, less a $200.00 deposit) do not match the server summary grand totals ($1000.00). Re-check both before completing.",
    );
  });

  it("keeps useful fallbacks when context is absent or unusable", () => {
    expect(errorMessage("UPLOAD_TOO_LARGE", {})).toBe(
      "The file exceeds the size limit.",
    );
    // Both totals or neither: an older backend sends an empty context.
    expect(errorMessage("RECONCILE_CARD_PAYMENT_MISMATCH", {})).toBe(
      "The TouchBistro card payments do not match the server summary grand totals. Re-check both before completing.",
    );
    expect(
      errorMessage("RECONCILE_CARD_PAYMENT_MISMATCH", {
        cardPaymentTotal: "1234.56",
      }),
    ).toBe(
      "The TouchBistro card payments do not match the server summary grand totals. Re-check both before completing.",
    );
    expect(
      errorMessage("UPLOAD_TOO_LARGE", { maxSizeMb: { unexpected: true } }),
    ).toBe("The file exceeds the size limit.");
    expect(errorMessage("RATE_LIMITED", {})).toBe(
      "Too many attempts. Please wait a moment and try again.",
    );
  });

  it.each(["NEW_BACKEND_CODE", "toString", "__proto__"])(
    "falls back safely for an unknown code (%s)",
    (code) => {
      expect(errorMessage(code as ErrorCode, {})).toBe("Something went wrong.");
    },
  );
});

describe("validation messages", () => {
  it.each<[string, ErrorContext, string]>([
    ["greater_than", { gt: 0 }, "Must be greater than 0."],
    ["greater_than_equal", { ge: 0 }, "Must be at least 0."],
    [
      "less_than",
      { lt: "1.000000000000000001" },
      "Must be less than 1.000000000000000001.",
    ],
    ["less_than_equal", { le: 5 }, "Must be at most 5."],
    ["string_too_short", { minLength: 3 }, "Minimum 3 characters required."],
    ["string_too_long", { maxLength: 200 }, "Maximum 200 characters allowed."],
    ["too_short", { minLength: 2 }, "At least 2 items required."],
    ["too_long", { maxLength: 4 }, "At most 4 items allowed."],
    [
      "enum",
      { expected: "'staff' or 'admin'" },
      "Choose from: 'staff' or 'admin'.",
    ],
    ["multiple_of", { multipleOf: "0.05" }, "Must be a multiple of 0.05."],
    [
      "decimal_max_places",
      { decimalPlaces: 2 },
      "Use at most 2 decimal places.",
    ],
    ["missing", {}, "This field is required."],
    ["greater_than", {}, "Too small."],
    ["string_too_short", { minLength: [] }, "Too short."],
    ["value_error", { error: "private diagnostic" }, "Invalid value."],
    ["unknown_validator", {}, "Invalid value."],
  ])("renders %s from its context", (code, ctx, message) => {
    expect(validationMessage({ code, path: ["field"], ctx })).toBe(message);
  });
});
