import type { ReactNode } from "react";

import { Dialog } from "@/components/dialog";
import { Button } from "@/components/ui";

/**
 * A simple yes/no confirmation modal built on {@link Dialog}: a message and
 * two equal-width actions. Reuses the shared `Button` primitive — the
 * `confirmTone` variant is all the styling this needs.
 */
export function ConfirmDialog({
  open,
  onClose,
  title,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  confirmTone = "primary",
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmTone?: "primary" | "danger";
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <div className="space-y-4">
        <div className="text-ink-muted text-sm">{children}</div>
        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button variant={confirmTone} className="flex-1" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
