import { useEffect, useRef, type ReactNode } from "react";

import { cx } from "@/lib/cx";

/**
 * Native `<dialog>`-based modal: focus trapping, Esc handling, and the
 * backdrop come from the platform. `dismissible: false` prevents native
 * cancellation with Esc; callers can still close the dialog.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  dismissible = true,
  maxWidth = "max-w-sm",
}: {
  open: boolean;
  onClose?: () => void;
  title: string;
  children: ReactNode;
  dismissible?: boolean;
  /** Width cap as a Tailwind class; replaces (never merges with) the default. */
  maxWidth?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-label={title}
      onCancel={(event) => {
        if (!dismissible) event.preventDefault();
      }}
      onClose={() => onClose?.()}
      className={cx(
        "border-line bg-surface text-ink m-auto w-[calc(100vw-2rem)]",
        maxWidth,
        "rounded-2xl border p-5 shadow-lg backdrop:bg-black/50",
        // Fade + slight zoom on open/close. Discrete display/overlay
        // transitions keep the closing dialog rendered until the fade ends;
        // browsers without @starting-style fall back to instant open/close.
        "scale-95 opacity-0 transition-[display,overlay,opacity,scale] transition-discrete duration-150 ease-out",
        "open:scale-100 open:opacity-100 starting:open:scale-95 starting:open:opacity-0",
        "backdrop:opacity-0 backdrop:transition-[display,overlay,opacity] backdrop:transition-discrete backdrop:duration-150 backdrop:ease-out",
        "open:backdrop:opacity-100 starting:open:backdrop:opacity-0",
        "motion-reduce:transition-none motion-reduce:backdrop:transition-none",
      )}
    >
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      {children}
    </dialog>
  );
}
