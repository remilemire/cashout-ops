// frontend/src/auth/CodeInput.test.tsx

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CodeInput } from "./CodeInput";

const onComplete = vi.fn();

function renderInput(props: { disabled?: boolean } = {}) {
  render(<CodeInput onComplete={onComplete} {...props} />);
  return screen.getAllByLabelText(/^Digit \d$/) as HTMLInputElement[];
}

beforeEach(() => {
  onComplete.mockReset();
});

describe("CodeInput", () => {
  it("renders one input per digit", () => {
    const inputs = renderInput();
    expect(inputs).toHaveLength(6);
  });

  it("ignores non-digit characters", async () => {
    const user = userEvent.setup();
    const inputs = renderInput();

    await user.click(inputs[0]!);
    await user.keyboard("a");
    expect(inputs[0]!.value).toBe("");

    await user.keyboard("5");
    expect(inputs[0]!.value).toBe("5");
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("advances focus to the next box after a digit is entered", async () => {
    const user = userEvent.setup();
    const inputs = renderInput();

    await user.click(inputs[0]!);
    await user.keyboard("1");

    expect(inputs[0]!.value).toBe("1");
    expect(document.activeElement).toBe(inputs[1]);
  });

  it("invokes onComplete once all six digits are entered", async () => {
    const user = userEvent.setup();
    const inputs = renderInput();

    // Enter one digit per box, awaiting each keystroke so the boxes re-render
    // between entries (mirroring how a person types the code in).
    for (const [index, digit] of [..."123456"].entries()) {
      await user.type(inputs[index]!, digit);
    }

    expect(onComplete).toHaveBeenCalledExactlyOnceWith("123456");
    expect(inputs[5]!.value).toBe("6");
  });

  it("fills every box from a paste and invokes onComplete", async () => {
    const user = userEvent.setup();
    const inputs = renderInput();

    await user.click(inputs[0]!);
    await user.paste("123456");

    expect(inputs.map((input) => input.value)).toEqual([..."123456"]);
    expect(onComplete).toHaveBeenCalledExactlyOnceWith("123456");
  });

  it("disables every box when disabled", () => {
    const inputs = renderInput({ disabled: true });

    expect(inputs.every((input) => input.disabled)).toBe(true);
  });
});
