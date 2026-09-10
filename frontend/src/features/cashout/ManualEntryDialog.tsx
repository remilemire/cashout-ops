import { Check, FolderOpen } from "lucide-react";
import { useRef, useState } from "react";

import { ApiError } from "@/api/client";
import {
  CASHOUT_DOCUMENT_CLASSIFICATIONS,
  DOCUMENT_CONTENT_TYPES,
  type CashoutDocumentClassification,
  type ManualEntryInput,
} from "@/api/types";
import { Dialog } from "@/components/dialog";
import { Button, ErrorBanner, TextField } from "@/components/ui";

import {
  CLASSIFICATION_LABELS,
  CLASSIFICATION_SCHEMA_NAMES,
  fieldGroupsFor,
} from "./fields";

/** "grand_total" → "grandTotal": the backend camelCases validation paths. */
function toCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, char: string) => char.toUpperCase());
}

function classificationOrDefault(
  value: CashoutDocumentClassification | null | undefined,
): CashoutDocumentClassification {
  return value ?? CASHOUT_DOCUMENT_CLASSIFICATIONS[0]!;
}

/**
 * Manual document details: the cashier picks the document type and types its
 * values in — no AI extraction runs. Presentational; the caller owns the
 * mutation and closes the dialog on success.
 */
export function ManualEntryDialog({
  open,
  onClose,
  withFile,
  initialClassification,
  pending,
  error,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  /** Whether a file must be attached (new upload vs. existing analysis). */
  withFile: boolean;
  initialClassification?: CashoutDocumentClassification | null;
  pending: boolean;
  error: unknown;
  onSubmit: (input: ManualEntryInput, file: File | null) => void;
}) {
  const [classification, setClassification] =
    useState<CashoutDocumentClassification>(() =>
      classificationOrDefault(initialClassification),
    );
  const [values, setValues] = useState<Record<string, string>>({});
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // A fresh form every time the dialog opens (the render-phase reset pattern:
  // react.dev "adjusting some state when a prop changes").
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) {
      setClassification(classificationOrDefault(initialClassification));
      setValues({});
      setFile(null);
    }
  }

  const groups = fieldGroupsFor(CLASSIFICATION_SCHEMA_NAMES[classification]);
  // A single group renders as a flat list, headings only differentiate.
  const showHeadings = groups.length > 1;
  const fieldKeys = groups.flatMap((group) =>
    group.fields.map((field) => field.key),
  );

  const fieldError = (key: string): string | undefined =>
    error instanceof ApiError ? error.messageFor(toCamel(key)) : undefined;
  // Issues that landed on a rendered control surface there; anything else
  // (or a non-validation failure) falls back to the banner.
  const coveredPaths = new Set([...fieldKeys.map(toCamel), "classification"]);
  const bannerError =
    error instanceof ApiError &&
    error.issues.length > 0 &&
    error.issues.every((issue) => coveredPaths.has(String(issue.path.at(-1))))
      ? null
      : error;

  const submit = () => {
    const data = Object.fromEntries(
      fieldKeys.map((key) => [key, values[key] ?? ""]),
    );
    onSubmit({ classification, data }, file);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Enter document details"
      // Wide enough for the action row to keep both labels on one line.
      maxWidth="max-w-md"
    >
      <div className="space-y-4">
        <p className="text-ink-muted text-sm">
          Type the document&rsquo;s values in yourself — no AI extraction runs.
        </p>

        <label className="block">
          <span className="mb-1 block text-sm font-medium">Document type</span>
          <select
            className="bg-surface border-line focus:ring-accent/50 h-11 w-full rounded-lg border px-3 text-sm outline-none focus:ring-2"
            value={classification}
            onChange={(event) => {
              setClassification(
                event.target.value as CashoutDocumentClassification,
              );
              // A different type is a different schema — start its form blank.
              setValues({});
            }}
          >
            {CASHOUT_DOCUMENT_CLASSIFICATIONS.map((value) => (
              <option key={value} value={value}>
                {CLASSIFICATION_LABELS[value]}
              </option>
            ))}
          </select>
          {error instanceof ApiError && error.messageFor("classification") && (
            <span className="text-danger mt-1 block text-xs">
              {error.messageFor("classification")}
            </span>
          )}
        </label>

        {withFile && (
          <div>
            <input
              ref={fileRef}
              type="file"
              accept={DOCUMENT_CONTENT_TYPES.join(",")}
              hidden
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                event.target.value = "";
              }}
            />
            <Button
              variant="outline"
              className="w-full"
              onClick={() => fileRef.current?.click()}
            >
              <FolderOpen className="size-4" />
              {file ? file.name : "Choose file"}
            </Button>
          </div>
        )}

        <div className="space-y-5">
          {groups.map((group) => (
            <div key={group.heading ?? "other"} className="space-y-2.5">
              {showHeadings && group.heading != null && (
                <p className="text-ink-muted text-xs font-semibold tracking-wider uppercase">
                  {group.heading}
                </p>
              )}
              {group.fields.map(({ key, label }) => (
                <TextField
                  key={key}
                  label={label}
                  inputMode="decimal"
                  value={values[key] ?? ""}
                  error={fieldError(key)}
                  onChange={(event) =>
                    setValues((prev) => ({
                      ...prev,
                      [key]: event.target.value,
                    }))
                  }
                />
              ))}
            </div>
          ))}
        </div>

        <ErrorBanner error={bannerError} />

        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" onClick={onClose}>
            Cancel
          </Button>
          <Button
            className="flex-1"
            loading={pending}
            disabled={withFile && file == null}
            onClick={submit}
          >
            <Check className="size-4" />
            Add details
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
