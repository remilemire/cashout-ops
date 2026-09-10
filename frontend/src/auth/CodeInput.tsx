import { useState, type ChangeEvent } from "react";

import { cx } from "@/lib/cx";

/** Number of digits in a login code (mirrors the backend). */
const DEFAULT_LENGTH = 6;

/**
 * Code input drawn as one box per digit but backed by a single `<input>`, so
 * autofill and paste hand the whole code to one field (per-digit inputs broke
 * macOS one-time-code autofill and Firefox paste). The input sits invisibly
 * over the boxes, which mirror its value. Invokes `onComplete` once every
 * digit is present; the parent resets it by remounting (changing `key`).
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
  const [code, setCode] = useState("");
  const [focused, setFocused] = useState(false);

  // No maxLength on the input: it would truncate a paste like "123-456"
  // before the non-digits are stripped here. Cleaning and slicing in the
  // change handler keeps every digit of such a paste.
  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    const cleaned = event.target.value.replace(/\D/g, "").slice(0, length);
    if (cleaned === code) return;
    setCode(cleaned);
    if (cleaned.length === length && !disabled) onComplete(cleaned);
  };

  /** Pin the caret to the end so typing always appends, Backspace always
   * deletes the last digit, and the boxes fill strictly left to right. */
  const snapCaretToEnd = (input: HTMLInputElement) => {
    const end = input.value.length;
    if (input.selectionStart !== end || input.selectionEnd !== end) {
      input.setSelectionRange(end, end);
    }
  };

  // The box the next digit will land in — carries the simulated focus ring.
  const activeIndex = Math.min(code.length, length - 1);

  return (
    <div className="relative">
      <input
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]*"
        aria-label="Sign-in code"
        disabled={disabled}
        value={code}
        onChange={onChange}
        onFocus={(event) => {
          setFocused(true);
          snapCaretToEnd(event.currentTarget);
        }}
        onBlur={() => setFocused(false)}
        onSelect={(event) => snapCaretToEnd(event.currentTarget)}
        className="absolute inset-0 h-full w-full opacity-0"
      />
      <div aria-hidden className="pointer-events-none flex gap-2">
        {Array.from({ length }, (_, index) => (
          <div
            key={index}
            className={cx(
              "bg-surface flex h-12 min-w-0 flex-1 items-center justify-center rounded-lg border text-lg font-semibold",
              error ? "border-danger" : "border-line",
              disabled && "opacity-50",
              focused && index === activeIndex && "ring-accent/50 ring-2",
            )}
          >
            {code[index] ??
              // The real caret is invisible along with its input, so the
              // empty active box blinks a simulated one.
              (focused && !disabled && index === activeIndex && (
                <span className="animate-caret-blink bg-ink h-6 w-px" />
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}
