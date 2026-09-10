/**
 * CSV serialization plus the browser download that hands the file to the
 * user. The download side effect is isolated in this module so pages can mock
 * it in tests: jsdom has no object URLs and does not navigate on click.
 */

/**
 * Excel needs the byte-order mark to decode UTF-8 (accented names otherwise
 * come out garbled); Google Sheets ignores it.
 */
const UTF8_BOM = "\uFEFF";

/**
 * RFC 4180: a field containing a comma, double quote, CR or LF is wrapped in
 * double quotes with inner quotes doubled; other fields are written bare.
 * Records end with CRLF, the last one included. No rows yields "".
 */
export function serializeCsv(rows: readonly (readonly string[])[]): string {
  return rows.map((row) => `${row.map(escapeField).join(",")}\r\n`).join("");
}

function escapeField(field: string): string {
  return /[",\r\n]/.test(field) ? `"${field.replaceAll('"', '""')}"` : field;
}

/** Serializes `rows` and downloads the result as `fileName`. */
export function downloadCsv(
  fileName: string,
  rows: readonly (readonly string[])[],
): void {
  const blob = new Blob([UTF8_BOM + serializeCsv(rows)], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  // Firefox only honors the click while the anchor is in the document.
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
