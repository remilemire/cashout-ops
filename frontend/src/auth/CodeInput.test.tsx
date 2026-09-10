import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CodeInput } from "./CodeInput";

const onComplete = vi.fn();

function renderInput(props: { disabled?: boolean } = {}) {
  render(<CodeInput onComplete={onComplete} {...props} />);
  return screen.getByLabelText("Sign-in code") as HTMLInputElement;
}

beforeEach(() => {
  onComplete.mockReset();
});

describe("CodeInput", () => {
  it("backs the six boxes with a single input", () => {
    const input = renderInput();

    expect(screen.getAllByRole("textbox")).toEqual([input]);
    expect(input.autocomplete).toBe("one-time-code");
  });

  it("ignores non-digit characters", async () => {
    const user = userEvent.setup();
    const input = renderInput();

    await user.click(input);
    await user.keyboard("a");
    expect(input.value).toBe("");

    await user.keyboard("5");
    expect(input.value).toBe("5");
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("mirrors typed digits into the visual boxes", async () => {
    const user = userEvent.setup();
    const input = renderInput();

    await user.type(input, "12");

    expect(screen.getByText("1")).toBeDefined();
    expect(screen.getByText("2")).toBeDefined();
  });

  it("invokes onComplete once all six digits are entered", async () => {
    const user = userEvent.setup();
    const input = renderInput();

    await user.type(input, "123456");

    expect(onComplete).toHaveBeenCalledExactlyOnceWith("123456");
    expect(input.value).toBe("123456");
  });

  it("caps the code at six digits without re-firing onComplete", async () => {
    const user = userEvent.setup();
    const input = renderInput();

    await user.type(input, "1234567");

    expect(input.value).toBe("123456");
    expect(onComplete).toHaveBeenCalledExactlyOnceWith("123456");
  });

  it("fills the code from a paste and invokes onComplete", async () => {
    const user = userEvent.setup();
    const input = renderInput();

    await user.click(input);
    await user.paste("123456");

    expect(input.value).toBe("123456");
    expect(onComplete).toHaveBeenCalledExactlyOnceWith("123456");
  });

  it("keeps every digit of a paste that carries separators", async () => {
    const user = userEvent.setup();
    const input = renderInput();

    await user.click(input);
    await user.paste("123-456");

    expect(input.value).toBe("123456");
    expect(onComplete).toHaveBeenCalledExactlyOnceWith("123456");
  });

  it("disables the input when disabled", () => {
    const input = renderInput({ disabled: true });

    expect(input.disabled).toBe(true);
  });
});
