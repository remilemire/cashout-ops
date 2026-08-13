// frontend/src/lib/format.test.ts

import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";

import {
  buildVerifiedData,
  coerceLike,
  enumLabel,
  fieldLabel,
  formatConfidence,
} from "./format";

describe("format helpers", () => {
  it("labels enums and fields", () => {
    expect(enumLabel("needs_verification")).toBe("Needs verification");
    expect(fieldLabel("dailyTipout")).toBe("Daily tipout");
    expect(fieldLabel("net_total")).toBe("Net total");
  });

  it("formats confidence", () => {
    expect(formatConfidence(0.954)).toBe("95%");
    expect(formatConfidence(null)).toBe("—");
  });

  it("coerces corrections toward the original JSON type", () => {
    expect(coerceLike(12.5, "13.25")).toBe(13.25);
    expect(coerceLike(12.5, "not a number")).toBe("not a number");
    expect(coerceLike(true, "false")).toBe(false);
    expect(coerceLike("note", "edited")).toBe("edited");
    expect(coerceLike(null, "")).toBe(null);
  });
});

describe("buildVerifiedData", () => {
  const extracted = { note: "cash $100", total: 12.5 };

  it("returns undefined when nothing changed", () => {
    expect(buildVerifiedData(extracted, {})).toBeUndefined();
    // Touching a field without changing its displayed value is not an edit.
    expect(buildVerifiedData(extracted, { total: "12.5" })).toBeUndefined();
  });

  it("merges edits and preserves the untouched values' types", () => {
    expect(buildVerifiedData(extracted, { total: "13" })).toEqual({
      note: "cash $100",
      total: 13,
    });
  });

  it("keeps non-numeric corrections as strings", () => {
    expect(buildVerifiedData(extracted, { total: "unreadable" })).toEqual({
      note: "cash $100",
      total: "unreadable",
    });
  });
});

describe("ApiError", () => {
  it("exposes field issues from the error contract", () => {
    const error = new ApiError(422, {
      kind: "VALIDATION",
      code: "VALIDATION_FAILED",
      message: "There was a problem with the submission.",
      issues: [
        {
          code: "TOO_SHORT",
          message: "Minimum 8 characters required.",
          path: ["password"],
        },
      ],
    });
    expect(error.messageFor("password")).toBe("Minimum 8 characters required.");
    expect(error.messageFor("email")).toBeUndefined();
    expect(error.message).toBe("There was a problem with the submission.");
  });
});
