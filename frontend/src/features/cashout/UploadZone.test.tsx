// frontend/src/features/cashout/UploadZone.test.tsx

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadZone } from "./UploadZone";

const pdf = new File(["%PDF-1.4"], "receipt.pdf", { type: "application/pdf" });

describe("UploadZone", () => {
  it("hands a dropped file to onFile", () => {
    const onFile = vi.fn();
    render(<UploadZone onFile={onFile} pending={false} error={null} />);

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });

    expect(onFile).toHaveBeenCalledWith(pdf);
  });

  it("ignores drops while an upload is pending", () => {
    const onFile = vi.fn();
    render(<UploadZone onFile={onFile} pending error={null} />);

    fireEvent.drop(screen.getByLabelText("Upload a document"), {
      dataTransfer: { files: [pdf] },
    });

    expect(onFile).not.toHaveBeenCalled();
    const takePhoto = screen.getByRole("button", {
      name: /take photo/i,
    }) as HTMLButtonElement;
    expect(takePhoto.disabled).toBe(true);
  });
});
