// frontend/src/lib/format.ts

const dateTime = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

const dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

/**
 * The given date (default: now) as YYYY-MM-DD in LOCAL time. Not
 * toISOString(): that renders the UTC day, which during the evening in a
 * negative-offset timezone is already tomorrow — the wrong day.
 */
export function localISODate(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Medium date display for a date-ONLY "YYYY-MM-DD" string. Not fed straight
 * to `new Date(...)`: that parses as UTC midnight, which Intl then renders in
 * the local zone — the previous day anywhere west of UTC — so the parts are
 * rebuilt into a local date first.
 */
export function formatDate(isoDate: string): string {
  const [year = 0, month = 1, day = 1] = isoDate.split("-").map(Number);
  return dateOnly.format(new Date(year, month - 1, day));
}

/** 0.95 → "95%" */
export function formatConfidence(value: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

/** "Ada Lovelace" → "AL"; a single word → its first two letters. */
export function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  const first = parts.at(0) ?? "";
  const last = parts.at(-1) ?? "";
  if (parts.length <= 1) return first.slice(0, 2).toUpperCase();
  return (first.charAt(0) + last.charAt(0)).toUpperCase();
}

/** "needs_verification" → "Needs verification" */
export function enumLabel(value: string): string {
  const lower = value.replaceAll("_", " ").toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/** "dailyTipout" / "daily_tipout" → "Daily tipout" */
export function fieldLabel(key: string): string {
  const spaced = key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Coerce an edited string back toward the original value's JSON type, so a
 * corrected number stays a number. Falls back to the raw string.
 */
export function coerceLike(original: unknown, edited: string): unknown {
  if (typeof original === "number") {
    const parsed = Number(edited);
    if (edited.trim() !== "" && Number.isFinite(parsed)) return parsed;
  }
  if (typeof original === "boolean") {
    if (edited === "true") return true;
    if (edited === "false") return false;
  }
  if (original === null && edited.trim() === "") return null;
  return edited;
}

/** Display an extracted JSON value as an editable/readable string. */
export function displayValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * Merge the cashier's textual edits into the extracted data, preserving the
 * original JSON types where possible. Returns undefined when nothing changed,
 * so an as-is confirmation sends no corrections.
 */
export function buildVerifiedData(
  extracted: Record<string, unknown>,
  edits: Record<string, string>,
): Record<string, unknown> | undefined {
  const changed = Object.entries(edits).filter(
    ([key, value]) => value !== displayValue(extracted[key]),
  );
  if (changed.length === 0) return undefined;

  const editedKeys = new Set(changed.map(([key]) => key));
  return Object.fromEntries(
    Object.entries(extracted).map(([key, value]) => [
      key,
      editedKeys.has(key) ? coerceLike(value, edits[key] ?? "") : value,
    ]),
  );
}
