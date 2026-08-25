// frontend/src/features/cashout/UploadZone.tsx

import { Camera, FolderOpen, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";

import { Button, ErrorBanner } from "@/components/ui";
import { cx } from "@/lib/cx";

const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp,application/pdf";

/**
 * Mobile-first document intake: camera capture and file picker buttons, with
 * drag-and-drop for desktops. One file per upload (matches the API).
 */
export function UploadZone({
  onFile,
  pending,
  error,
}: {
  onFile: (file: File) => void;
  pending: boolean;
  error: unknown;
}) {
  const cameraRef = useRef<HTMLInputElement>(null);
  const pickerRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0];
    if (file && !pending) onFile(file);
  };

  return (
    <section
      aria-label="Upload a document"
      onDragOver={(event) => {
        event.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragOver(false);
        handleFiles(event.dataTransfer.files);
      }}
      className={cx(
        "rounded-xl border-2 border-dashed p-4 text-center transition-colors",
        dragOver ? "border-accent bg-accent/5" : "border-line bg-surface",
      )}
    >
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = "";
        }}
      />
      <input
        ref={pickerRef}
        type="file"
        accept={ACCEPTED_TYPES}
        hidden
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = "";
        }}
      />

      <UploadCloud
        className="text-ink-muted mx-auto size-7"
        strokeWidth={1.5}
      />
      <p className="mt-2 text-sm font-medium">Add a document</p>
      <p className="text-ink-muted mt-0.5 text-xs">
        Shift report, terminal report, receipt, tip-out sheet, or cash summary.
        JPEG, PNG, WebP, or PDF.
      </p>

      <div className="mt-3 flex flex-col justify-center gap-2 sm:flex-row">
        <Button
          variant="primary"
          loading={pending}
          onClick={() => cameraRef.current?.click()}
        >
          <Camera className="size-4" />
          Take photo
        </Button>
        <Button
          variant="outline"
          disabled={pending}
          onClick={() => pickerRef.current?.click()}
        >
          <FolderOpen className="size-4" />
          Choose file
        </Button>
      </div>

      {error != null && (
        <div className="mt-3 text-left">
          <ErrorBanner error={error} />
        </div>
      )}
    </section>
  );
}
