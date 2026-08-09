// frontend/src/auth/CodeInput.tsx

import {
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
} from "react";

import { cx } from "@/lib/cx";

/** Number of digits in a login code (mirrors the backend). */
const DEFAULT_LENGTH = 6;

/**
 * One-box-per-digit code input. Invokes `onComplete` once every box holds a
 * digit; the parent resets it by remounting (changing `key`).
 */
export function CodeInput({
  length = DEFAULT_LENGTH,
  disabled = false,
  error = false,
  onComplete,
}: {
  length?: number;
  disabled?: boolean;
  /** Paint the boxes in the danger tone (e.g. after a rejected code). */
  error?: boolean;
  onComplete: (code: string) => void;
}) {
  const [digits, setDigits] = useState<string[]>(() =>
    Array.from({ length }, () => ""),
  );
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);

  const focusInput = (index: number) => {
    const input = inputsRef.current[index];
    input?.focus();
    input?.select();
  };

  const commit = (next: string[], focusIndex: number) => {
    setDigits(next);
    focusInput(focusIndex);
    if (next.every(Boolean) && !disabled) onComplete(next.join(""));
  };

  /** Write `raw`'s digits into the boxes starting at `start`, ignoring
   * non-digits. Used for both single keystrokes and multi-digit pastes. */
  const fillFrom = (start: number, raw: string) => {
    const chars = raw.replace(/\D/g, "");
    const next = [...digits];
    let cursor = start;
    for (const char of chars) {
      if (cursor >= length) break;
      next[cursor] = char;
      cursor += 1;
    }
    commit(next, Math.min(cursor, length - 1));
  };

  const onDigitChange = (index: number, raw: string) => {
    const cleaned = raw.replace(/\D/g, "");
    if (cleaned.length > 1) {
      // Autofill / one-time-code can drop the whole code into a single box.
      fillFrom(index, cleaned);
      return;
    }
    const next = [...digits];
    next[index] = cleaned;
    commit(next, cleaned ? Math.min(index + 1, length - 1) : index);
  };

  const onDigitKeyDown = (
    index: number,
    event: KeyboardEvent<HTMLInputElement>,
  ) => {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      // Nothing to delete here: step back and clear the previous box.
      event.preventDefault();
      const next = [...digits];
      next[index - 1] = "";
      setDigits(next);
      focusInput(index - 1);
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      focusInput(index - 1);
    } else if (event.key === "ArrowRight" && index < length - 1) {
      event.preventDefault();
      focusInput(index + 1);
    }
  };

  const onDigitPaste = (
    index: number,
    event: ClipboardEvent<HTMLInputElement>,
  ) => {
    event.preventDefault();
    fillFrom(index, event.clipboardData.getData("text"));
  };

  return (
    <div
      role="group"
      aria-label="Sign-in code"
      className="flex justify-between gap-2"
    >
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(element) => {
            inputsRef.current[index] = element;
          }}
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          pattern="[0-9]*"
          maxLength={1}
          aria-label={`Digit ${index + 1}`}
          disabled={disabled}
          value={digit}
          onChange={(event) => onDigitChange(index, event.target.value)}
          onKeyDown={(event) => onDigitKeyDown(index, event)}
          onPaste={(event) => onDigitPaste(index, event)}
          onFocus={(event) => event.currentTarget.select()}
          className={cx(
            "bg-surface size-11 min-w-0 flex-1 rounded-lg border text-center text-lg font-semibold",
            "focus:ring-accent/50 outline-none focus:ring-2 disabled:opacity-50",
            error ? "border-danger" : "border-line",
          )}
        />
      ))}
    </div>
  );
}
