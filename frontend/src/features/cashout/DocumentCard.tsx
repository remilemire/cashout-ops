// frontend/src/features/cashout/DocumentCard.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  FileText,
  Pencil,
  RefreshCw,
  ScanLine,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import {
  CASHOUT_DOCUMENT_CLASSIFICATIONS,
  type CashoutDocument,
  type CashoutDocumentClassification,
} from "@/api/types";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Dialog } from "@/components/dialog";
import { Button, Card, ErrorBanner, Spinner } from "@/components/ui";
import { formatDateTime } from "@/lib/format";

import { FieldList } from "./FieldList";
import { CLASSIFICATION_LABELS } from "./fields";
import { VerificationForm } from "./VerificationForm";
import { AnalysisStatusBadge } from "./status";

/**
 * One uploaded document with its analysis lifecycle: polls the analysis while
 * the background extraction runs, then renders the state-appropriate step
 * (verify, retry, or the verified summary).
 */
export function DocumentCard({
  document,
  submissionId,
  editable,
}: {
  document: CashoutDocument;
  submissionId: string;
  editable: boolean;
}) {
  const queryClient = useQueryClient();
  const [removeOpen, setRemoveOpen] = useState(false);
  const [classifyOpen, setClassifyOpen] = useState(false);
  const [classification, setClassification] =
    useState<CashoutDocumentClassification>("unknown");
  const initial = document.analysis;

  // Poll the analysis while the AI extraction runs in the background.
  const analysisQuery = useQuery({
    queryKey: cashoutKeys.analysis(initial?.id ?? "missing"),
    queryFn: () => cashoutApi.getAnalysis(initial!.id),
    enabled: initial != null,
    initialData: initial ?? undefined,
    staleTime: Infinity,
    refetchInterval: (query) =>
      query.state.data?.status === "extracting" ? 1500 : false,
  });
  const analysis = analysisQuery.data ?? initial;

  // When extraction settles, the submission detail (document type, statuses)
  // is stale — refresh it.
  const liveStatus = analysis?.status;
  const detailStatus = initial?.status;
  useEffect(() => {
    if (liveStatus && liveStatus !== detailStatus) {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    }
  }, [liveStatus, detailStatus, queryClient, submissionId]);

  const retry = useMutation({
    mutationFn: () => cashoutApi.extractDocument(document.id),
    onSuccess: (updated) => {
      queryClient.setQueryData(cashoutKeys.analysis(updated.id), updated);
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
  });

  // The user corrects a misclassification: the backend re-extracts as the
  // chosen type (skipping the AI classify step) and the card polls as usual.
  const reclassify = useMutation({
    mutationFn: (value: CashoutDocumentClassification) =>
      cashoutApi.extractDocument(document.id, { classification: value }),
    onSuccess: (updated) => {
      queryClient.setQueryData(cashoutKeys.analysis(updated.id), updated);
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
  });

  // "Edit" on a verified analysis: sends it back to needs-verification (the
  // extraction fields survive, so the verification form re-renders from them).
  const unverify = useMutation({
    mutationFn: () => cashoutApi.unverifyAnalysis(analysis!.id),
    onSuccess: (updated) => {
      queryClient.setQueryData(cashoutKeys.analysis(updated.id), updated);
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
  });

  const remove = useMutation({
    mutationFn: () => cashoutApi.deleteDocument(document.id),
    onSuccess: () => {
      // The analysis is gone with the document — drop its cache entry so
      // nothing keeps polling a 404.
      if (initial) {
        queryClient.removeQueries({
          queryKey: cashoutKeys.analysis(initial.id),
        });
      }
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
  });

  const isImage = document.contentType.startsWith("image/");
  const contentUrl = cashoutApi.documentContentUrl(document.id);
  // Correcting the classification only makes sense on a settled, unverified
  // extraction; other states keep the plain label.
  const canCorrectClassification =
    editable && analysis?.status === "needs_verification";

  return (
    <>
      <Card className="space-y-3">
        <div className="flex items-start gap-3">
          <a
            href={contentUrl}
            target="_blank"
            rel="noreferrer"
            title="View original"
            className="border-line bg-surface-2 block size-14 shrink-0 overflow-hidden rounded-lg border"
          >
            {isImage ? (
              <img
                src={contentUrl}
                alt={document.originalFilename}
                loading="lazy"
                className="size-full object-cover"
              />
            ) : (
              <span className="text-ink-muted grid size-full place-items-center">
                <FileText className="size-6" strokeWidth={1.5} />
              </span>
            )}
          </a>

          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{document.originalFilename}</p>
            <div className="flex items-center">
              <p className="text-ink-muted text-xs">
                {analysis?.classification
                  ? CLASSIFICATION_LABELS[analysis.classification]
                  : "Not classified yet"}
              </p>
              {canCorrectClassification && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Correct document type"
                  title="Correct document type"
                  className="text-ink-muted hover:text-ink -my-2 px-1.5"
                  loading={reclassify.isPending}
                  onClick={() => {
                    setClassification(analysis?.classification ?? "unknown");
                    setClassifyOpen(true);
                  }}
                >
                  <Pencil className="size-3" />
                </Button>
              )}
            </div>
            <a
              href={contentUrl}
              target="_blank"
              rel="noreferrer"
              className="text-accent-strong mt-0.5 inline-flex items-center gap-1 text-xs hover:underline"
            >
              View original <ExternalLink className="size-3" />
            </a>
          </div>

          {(analysis || editable) && (
            <div className="flex items-center gap-1">
              {analysis && <AnalysisStatusBadge status={analysis.status} />}
              {editable && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Remove document"
                  title="Remove document"
                  className="text-ink-muted hover:text-danger -my-2 -mr-1 px-2"
                  loading={remove.isPending}
                  onClick={() => setRemoveOpen(true)}
                >
                  <Trash2 className="size-4" />
                </Button>
              )}
            </div>
          )}
        </div>

        <ErrorBanner error={remove.error} />

        {!analysis && (
          <p className="text-ink-muted text-sm">
            No analysis for this document.
          </p>
        )}

        {analysis?.status === "extracting" && (
          <div className="bg-surface-2 flex items-center gap-3 rounded-lg px-3 py-3 text-sm">
            <Spinner className="size-4 shrink-0" />
            <div>
              <p className="font-medium">Reading the document…</p>
              <p className="text-ink-muted text-xs">
                The AI is classifying and extracting it. This can take a moment.
              </p>
            </div>
            <ScanLine className="text-ink-muted ml-auto size-5 animate-pulse" />
          </div>
        )}

        {analysis?.status === "failed" && (
          <div className="space-y-2">
            <div className="border-danger/30 bg-danger/10 rounded-lg border px-3 py-2 text-sm">
              <p className="text-danger font-medium">
                Extraction failed
                {analysis.errorCode ? ` (${analysis.errorCode})` : ""}
              </p>
              {analysis.errorMessage && (
                <p className="text-ink-muted mt-0.5">{analysis.errorMessage}</p>
              )}
            </div>
            {editable && (
              <Button
                variant="outline"
                className="w-full sm:w-auto"
                onClick={() => retry.mutate()}
                loading={retry.isPending}
              >
                <RefreshCw className="size-4" />
                Retry extraction
              </Button>
            )}
            <ErrorBanner error={retry.error} />
          </div>
        )}

        {analysis?.status === "needs_verification" && (
          <div className="space-y-2">
            <VerificationForm
              analysis={analysis}
              submissionId={submissionId}
              editable={editable}
              secondaryAction={
                <Button
                  variant="outline"
                  onClick={() => retry.mutate()}
                  loading={retry.isPending}
                >
                  <RefreshCw className="size-4" />
                  Retry extraction
                </Button>
              }
            />
            <ErrorBanner error={retry.error} />
            <ErrorBanner error={reclassify.error} />
          </div>
        )}

        {analysis?.status === "verified" && (
          <div className="space-y-2">
            <FieldList
              data={analysis.verifiedDataJson ?? {}}
              schemaName={analysis.schemaName}
            />
            <CorrectionNote
              extracted={analysis.extractedDataJson}
              verified={analysis.verifiedDataJson}
              schemaName={analysis.schemaName}
            />
            <p className="text-ink-muted text-xs">
              Verified{" "}
              {analysis.verifiedAt ? formatDateTime(analysis.verifiedAt) : ""}
            </p>
            {editable && (
              // Set apart from the verified summary above it.
              <Button
                variant="outline"
                className="mt-2"
                onClick={() => unverify.mutate()}
                loading={unverify.isPending}
              >
                <Pencil className="size-4" />
                Edit
              </Button>
            )}
            <ErrorBanner error={unverify.error} />
          </div>
        )}
      </Card>

      {/* Outside the card: a closed <dialog> renders no box, but as the last
          child it would take :last-child from the content above it and leave
          the card's space-y margin hanging below the last visible row. */}
      <ConfirmDialog
        open={removeOpen}
        onClose={() => setRemoveOpen(false)}
        title="Remove document?"
        confirmLabel="Remove document"
        cancelLabel="Keep document"
        confirmTone="danger"
        onConfirm={() => {
          remove.mutate();
          setRemoveOpen(false);
        }}
      >
        This permanently deletes {document.originalFilename} and its extracted
        data from this cashout. This can&rsquo;t be undone.
      </ConfirmDialog>

      <Dialog
        open={classifyOpen}
        onClose={() => setClassifyOpen(false)}
        title="Correct document type"
      >
        <div className="space-y-4">
          <p className="text-ink-muted text-sm">
            Re-runs the extraction as the selected type, replacing the current
            extracted values.
          </p>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">
              Document type
            </span>
            <select
              className="bg-surface border-line focus:ring-accent/50 min-h-11 w-full rounded-lg border px-3 text-sm outline-none focus:ring-2"
              value={classification}
              onChange={(event) =>
                setClassification(
                  event.target.value as CashoutDocumentClassification,
                )
              }
            >
              {CASHOUT_DOCUMENT_CLASSIFICATIONS.map((value) => (
                <option key={value} value={value}>
                  {CLASSIFICATION_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
          <div className="flex gap-3">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => setClassifyOpen(false)}
            >
              Cancel
            </Button>
            <Button
              className="flex-1"
              // Re-running with the same type would be the plain retry —
              // don't fire an identical extraction from a "correction".
              disabled={classification === analysis?.classification}
              onClick={() => {
                reclassify.mutate(classification);
                setClassifyOpen(false);
              }}
            >
              <RefreshCw className="size-4" />
              Re-run extraction
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

/** When the cashier corrected values, keep the original extraction reachable. */
function CorrectionNote({
  extracted,
  verified,
  schemaName,
}: {
  extracted: Record<string, unknown> | null;
  verified: Record<string, unknown> | null;
  schemaName: string | null;
}) {
  if (!extracted || !verified) return null;
  if (JSON.stringify(extracted) === JSON.stringify(verified)) return null;
  return (
    <details className="text-xs">
      <summary className="text-ink-muted cursor-pointer select-none">
        Corrected from the original extraction — show it
      </summary>
      <div className="border-line mt-2 rounded-lg border p-2">
        <FieldList data={extracted} schemaName={schemaName} />
      </div>
    </details>
  );
}
