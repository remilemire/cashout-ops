// frontend/src/components/dialog.tsx

import { useEffect, useRef, type ReactNode } from "react";

import { cx } from "./ui";

/**
 * Native `<dialog>`-based modal: focus trapping, Esc handling, and the
 * backdrop come from the platform. `dismissible: false` makes it blocking
 * (used by the email-verification gate).
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  dismissible = true,
}: {
  open: boolean;
  onClose?: () => void;
  title: string;
  children: ReactNode;
  dismissible?: boolean;
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
      onCancel={(event) => {
        if (!dismissible) event.preventDefault();
      }}
      onClose={() => onClose?.()}
      className={cx(
        "border-line bg-surface text-ink m-auto w-[calc(100vw-2rem)] max-w-sm",
        "rounded-2xl border p-5 shadow-lg backdrop:bg-black/50",
      )}
    >
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      {children}
    </dialog>
  );
}
