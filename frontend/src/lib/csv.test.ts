import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadCsv, serializeCsv } from "./csv";

describe("serializeCsv", () => {
  it("writes plain fields bare, joined by commas", () => {
    expect(serializeCsv([["a", "b", "c"]])).toBe("a,b,c\r\n");
  });

  it("quotes a field containing a comma", () => {
    expect(serializeCsv([["Doe, Jane", "1"]])).toBe('"Doe, Jane",1\r\n');
  });

  it("quotes a field containing double quotes and doubles them", () => {
    expect(serializeCsv([['the "Bar"']])).toBe('"the ""Bar"""\r\n');
  });

  it("quotes a field containing a newline", () => {
    expect(serializeCsv([["line 1\nline 2"]])).toBe('"line 1\nline 2"\r\n');
    expect(serializeCsv([["line 1\r\nline 2"]])).toBe('"line 1\r\nline 2"\r\n');
  });

  it("separates records with CRLF, including after the last one", () => {
    expect(
      serializeCsv([
        ["a", "b"],
        ["c", "d"],
      ]),
    ).toBe("a,b\r\nc,d\r\n");
  });

  it("yields an empty string for no rows", () => {
    expect(serializeCsv([])).toBe("");
  });
});

describe("downloadCsv", () => {
  const OBJECT_URL = "blob:csv";
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => OBJECT_URL);
  const revokeObjectURL = vi.fn<(url: string) => void>();
  // jsdom implements neither object URLs nor navigation from an anchor click.
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});

  beforeEach(() => {
    Object.assign(URL, { createObjectURL, revokeObjectURL });
  });

  afterEach(() => {
    Reflect.deleteProperty(URL, "createObjectURL");
    Reflect.deleteProperty(URL, "revokeObjectURL");
    vi.clearAllMocks();
  });

  it("clicks a temporary anchor named after the file, then cleans up", () => {
    downloadCsv("cashouts.csv", [["a", "b"]]);

    expect(click).toHaveBeenCalledOnce();
    const anchor = click.mock.contexts[0];
    expect(anchor).toBeInstanceOf(HTMLAnchorElement);
    expect(anchor).toHaveProperty("download", "cashouts.csv");
    expect(anchor).toHaveProperty("href", OBJECT_URL);
    expect(anchor).toHaveProperty("isConnected", false);
    expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith(OBJECT_URL);
  });

  it("hands a BOM-prefixed UTF-8 CSV blob to the object URL", async () => {
    downloadCsv("cashouts.csv", [
      ["Name", "Total"],
      ["Zoë", "12.50"],
    ]);

    expect(createObjectURL).toHaveBeenCalledOnce();
    const blob = createObjectURL.mock.calls[0]?.[0];
    expect(blob).toBeInstanceOf(Blob);
    expect(blob?.type).toBe("text/csv;charset=utf-8");
    // Blob.text() strips a leading BOM (the spec's "UTF-8 decode"), so decode
    // the raw bytes with the BOM kept to prove it was written.
    const decoded = new TextDecoder("utf-8", { ignoreBOM: true }).decode(
      await blob?.arrayBuffer(),
    );
    expect(decoded).toBe("\uFEFFName,Total\r\nZoë,12.50\r\n");
  });
});
