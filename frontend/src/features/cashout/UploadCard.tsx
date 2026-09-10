// frontend/src/features/cashout/UploadCard.tsx

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  FileText,
  Pencil,
  RefreshCw,
  ScanLine,
  ScanSearch,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cashoutApi, cashoutKeys } from "@/api/cashout";
import { isNotFound } from "@/api/client";
import {
  CASHOUT_DOCUMENT_CLASSIFICATIONS,
  DOCUMENT_CONTENT_TYPES,
  type CashoutUpload,
  type CashoutDocumentAnalysis,
  type CashoutDocumentClassification,
  type ManualEntryInput,
} from "@/api/types";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Dialog } from "@/components/dialog";
import { Button, Card, ErrorBanner, Spinner } from "@/components/ui";
import { formatDateTime } from "@/lib/format";

import { FieldList } from "./FieldList";
import { CLASSIFICATION_LABELS } from "./fields";
import { ManualEntryDialog } from "./ManualEntryDialog";
import { VerificationForm } from "./VerificationForm";
import { AnalysisStatusBadge } from "./status";

/**
 * One upload and the analysis of each document found in it. The header is the
 * upload itself — its preview, the original, removal, replacing it, starting
 * it over — and each analysis gets a panel of its own that polls it while the
 * background extraction runs, then renders the state-appropriate step
 * (verify, retry, or the verified summary).
 */
export function UploadCard({
  upload,
  submissionId,
  editable,
}: {
  upload: CashoutUpload;
  submissionId: string;
  editable: boolean;
}) {
  const queryClient = useQueryClient();
  const [removeOpen, setRemoveOpen] = useState(false);
  const [restartOpen, setRestartOpen] = useState(false);
  const [thumbnailBroken, setThumbnailBroken] = useState(false);
  const analyses = inPositionOrder(upload.analyses);
  const first = analyses[0];

  // A 404 out of any action on the card: the upload, an analysis, or the
  // submission was deleted elsewhere, so refresh instead of leaving stale UI.
  const refreshIfGone = (error: unknown) => {
    if (isNotFound(error)) {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    }
  };

  // The analyses are gone (with the upload, or with a restart) — drop
  // their cache entries so nothing keeps polling a 404.
  const forgetAnalyses = () => {
    for (const analysis of analyses) {
      queryClient.removeQueries({
        queryKey: cashoutKeys.analysis(analysis.id),
      });
    }
  };

  // Replace an upload whose extraction failed with a better shot of the
  // document (e.g. cropped after an output-limit failure). Upload before
  // delete: a rejected upload (unsupported type, too large, identical bytes)
  // leaves the failed original in place.
  const reuploadRef = useRef<HTMLInputElement>(null);
  const reupload = useMutation({
    mutationFn: async (file: File) => {
      const uploaded = await cashoutApi.createUpload(submissionId, file);
      await cashoutApi.deleteUpload(upload.id);
      return uploaded;
    },
    onSuccess: (uploaded) => {
      queryClient.setQueryData(cashoutKeys.analysis(uploaded.id), uploaded);
      forgetAnalyses();
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
    onError: refreshIfGone,
  });

  // Start the upload over: the backend discards every analysis and crop,
  // finds the documents in it again, and extracts each afresh — the way out
  // of a wrong split or crop. The fresh first analysis polls as usual; the
  // detail refresh brings in any siblings.
  const restart = useMutation({
    mutationFn: () => cashoutApi.restartUpload(upload.id),
    onSuccess: (fresh) => {
      forgetAnalyses();
      queryClient.setQueryData(cashoutKeys.analysis(fresh.id), fresh);
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
    onError: refreshIfGone,
  });

  const remove = useMutation({
    mutationFn: () => cashoutApi.deleteUpload(upload.id),
    onSuccess: () => {
      forgetAnalyses();
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    },
    onError: refreshIfGone,
  });

  const contentUrl = cashoutApi.uploadContentUrl(upload.id);
  // The upload's preview is the first document found in it, once there is a
  // crop of it; the original stays one link away. A crop is always an image.
  const croppedUrl = croppedUrlOf(first);
  const previewUrl = croppedUrl ?? contentUrl;
  const isImage = croppedUrl != null || upload.contentType.startsWith("image/");
  // Starting over discards every analysis, so it is offered only while none
  // of them is verified or still extracting (the backend refuses otherwise).
  const canRestart =
    editable &&
    analyses.length > 0 &&
    analyses.every(
      (analysis) =>
        analysis.status === "failed" ||
        analysis.status === "needs_verification",
    );

  return (
    <>
      <Card className="space-y-3">
        <div className="flex items-start gap-3">
          <a
            href={previewUrl}
            target="_blank"
            rel="noreferrer"
            title={
              croppedUrl != null ? "View cropped document" : "View original"
            }
            className="border-line bg-surface-2 block size-14 shrink-0 overflow-hidden rounded-lg border"
          >
            {isImage && !thumbnailBroken ? (
              <img
                src={previewUrl}
                alt={upload.originalFilename}
                loading="lazy"
                className="size-full object-cover"
                // The stored file can be gone even though the upload row
                // survives; fall back to the file icon over a broken image.
                onError={() => setThumbnailBroken(true)}
              />
            ) : (
              <span className="text-ink-muted grid size-full place-items-center">
                <FileText className="size-6" strokeWidth={1.5} />
              </span>
            )}
          </a>

          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{upload.originalFilename}</p>
            {analyses.length > 1 && (
              <p className="text-ink-muted text-xs">
                {analyses.length} documents found in this upload
              </p>
            )}
            <a
              href={contentUrl}
              target="_blank"
              rel="noreferrer"
              className="text-accent-strong mt-0.5 inline-flex items-center gap-1 text-xs hover:underline"
            >
              View original <ExternalLink className="size-3" />
            </a>
          </div>

          {editable && (
            <div className="flex items-center gap-1">
              {canRestart && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Detect documents again"
                  title="Detect documents again"
                  className="text-ink-muted hover:text-ink -my-2 px-2"
                  loading={restart.isPending}
                  onClick={() => setRestartOpen(true)}
                >
                  <ScanSearch className="size-4" />
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                aria-label="Remove upload"
                title="Remove upload"
                className="text-ink-muted hover:text-danger -my-2 -mr-1 px-2"
                loading={remove.isPending}
                onClick={() => setRemoveOpen(true)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          )}
        </div>

        <ErrorBanner error={remove.error} />
        <ErrorBanner error={restart.error} />
        <ErrorBanner error={reupload.error} />

        {analyses.length === 0 && (
          <p className="text-ink-muted text-sm">No analysis for this upload.</p>
        )}

        {analyses.map((analysis) => (
          <AnalysisPanel
            key={analysis.id}
            initial={analysis}
            count={analyses.length}
            contentUrl={contentUrl}
            submissionId={submissionId}
            editable={editable}
            replaceImage={{
              open: () => reuploadRef.current?.click(),
              pending: reupload.isPending,
            }}
          />
        ))}

        <input
          ref={reuploadRef}
          type="file"
          accept={DOCUMENT_CONTENT_TYPES.join(",")}
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file && !reupload.isPending) reupload.mutate(file);
            event.target.value = "";
          }}
        />
      </Card>

      {/* Outside the card: a closed <dialog> renders no box, but as the last
          child it would take :last-child from the content above it and leave
          the card's space-y margin hanging below the last visible row. */}
      <ConfirmDialog
        open={removeOpen}
        onClose={() => setRemoveOpen(false)}
        title="Remove this upload?"
        confirmLabel="Remove upload"
        cancelLabel="Keep"
        confirmTone="danger"
        onConfirm={() => {
          remove.mutate();
          setRemoveOpen(false);
        }}
      >
        This permanently deletes {upload.originalFilename} and its extracted
        data from this cashout. This can&rsquo;t be undone.
      </ConfirmDialog>

      <ConfirmDialog
        open={restartOpen}
        onClose={() => setRestartOpen(false)}
        title="Detect documents again?"
        confirmLabel="Detect again"
        cancelLabel="Keep as is"
        onConfirm={() => {
          restart.mutate();
          setRestartOpen(false);
        }}
      >
        Finds the documents in {upload.originalFilename} again and re-reads each
        of them, replacing every current extraction from it.
      </ConfirmDialog>
    </>
  );
}

/**
 * One document found in the upload: polls its analysis while the background
 * extraction runs, then renders the state-appropriate step. With several
 * documents in the upload, each panel shows its own crop and its place among
 * them.
 */
function AnalysisPanel({
  initial,
  count,
  contentUrl,
  submissionId,
  editable,
  replaceImage,
}: {
  initial: CashoutDocumentAnalysis;
  count: number;
  contentUrl: string;
  submissionId: string;
  editable: boolean;
  replaceImage: { open: () => void; pending: boolean };
}) {
  const queryClient = useQueryClient();
  const [classifyOpen, setClassifyOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [thumbnailBroken, setThumbnailBroken] = useState(false);
  const [classification, setClassification] =
    useState<CashoutDocumentClassification>(
      CASHOUT_DOCUMENT_CLASSIFICATIONS[0]!,
    );

  // Poll the analysis while the AI extraction runs in the background. A 404
  // means the analysis (or its upload or submission) was deleted elsewhere:
  // the resource is gone for good, so polling stops rather than retrying a
  // dead reference forever.
  const analysisQuery = useQuery({
    queryKey: cashoutKeys.analysis(initial.id),
    queryFn: () => cashoutApi.getAnalysis(initial.id),
    initialData: initial,
    staleTime: Infinity,
    refetchInterval: (query) =>
      query.state.data?.status === "extracting" &&
      !isNotFound(query.state.error)
        ? 1500
        : false,
  });
  const analysis = analysisQuery.data ?? initial;

  // When extraction settles, the submission detail (document type, statuses,
  // and any sibling analyses the job found) is stale — refresh it.
  const liveStatus = analysis.status;
  const detailStatus = initial.status;
  useEffect(() => {
    if (liveStatus !== detailStatus) {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    }
  }, [liveStatus, detailStatus, queryClient, submissionId]);

  // A dead analysis means the panel itself is stale: refresh the detail so
  // the removed upload disappears (or the page reports the cashout gone).
  const analysisGone = isNotFound(analysisQuery.error);
  useEffect(() => {
    if (analysisGone) {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    }
  }, [analysisGone, queryClient, submissionId]);

  const refreshIfGone = (error: unknown) => {
    if (isNotFound(error)) {
      void queryClient.invalidateQueries({
        queryKey: cashoutKeys.submission(submissionId),
      });
    }
  };
  const settle = (updated: CashoutDocumentAnalysis) => {
    queryClient.setQueryData(cashoutKeys.analysis(updated.id), updated);
    void queryClient.invalidateQueries({
      queryKey: cashoutKeys.submission(submissionId),
    });
  };

  const retry = useMutation({
    mutationFn: () => cashoutApi.retryExtraction(analysis.id),
    onSuccess: settle,
    onError: refreshIfGone,
  });

  // The user corrects a misclassification: the backend re-extracts as the
  // chosen type (skipping the AI classify step) and the panel polls as usual.
  const reclassify = useMutation({
    mutationFn: (value: CashoutDocumentClassification) =>
      cashoutApi.retryExtraction(analysis.id, { classification: value }),
    onSuccess: settle,
    onError: refreshIfGone,
  });

  // The user types the details in instead of the AI: the backend records the
  // entered values as the verified data (no extraction runs).
  const manualEntry = useMutation({
    mutationFn: (input: ManualEntryInput) =>
      cashoutApi.replaceWithManualEntry(analysis.id, input),
    onSuccess: (updated) => {
      settle(updated);
      setManualOpen(false);
    },
    onError: refreshIfGone,
  });

  // "Edit" on a verified analysis: sends it back to needs-verification (the
  // extraction fields survive, so the verification form re-renders from them).
  const unverify = useMutation({
    mutationFn: () => cashoutApi.unverifyAnalysis(analysis.id),
    onSuccess: settle,
    onError: refreshIfGone,
  });

  const croppedUrl = croppedUrlOf(analysis);
  // Correcting the classification only makes sense on a settled, unverified
  // extraction; other states keep the plain label.
  const canCorrectClassification =
    editable && analysis.status === "needs_verification";

  return (
    <div
      className={
        count > 1 ? "border-line space-y-2 rounded-lg border p-3" : "space-y-2"
      }
    >
      {/* First, not last: a closed <dialog> renders no box, so it must not
          take :last-child from the visible row above it. */}
      <Dialog
        open={classifyOpen}
        onClose={() => setClassifyOpen(false)}
        title="Correct document type"
        // Wide enough for the action row to keep both labels on one line.
        maxWidth="max-w-md"
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
              className="bg-surface border-line focus:ring-accent/50 h-11 w-full rounded-lg border px-3 text-sm outline-none focus:ring-2"
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
              disabled={classification === analysis.classification}
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

      <ManualEntryDialog
        open={manualOpen}
        onClose={() => setManualOpen(false)}
        withFile={false}
        initialClassification={analysis.classification ?? null}
        pending={manualEntry.isPending}
        error={manualEntry.error}
        onSubmit={(input) => manualEntry.mutate(input)}
      />

      <div className="flex items-center gap-2">
        {count > 1 && (
          <a
            href={croppedUrl ?? contentUrl}
            target="_blank"
            rel="noreferrer"
            title="View this document"
            className="border-line bg-surface-2 block size-10 shrink-0 overflow-hidden rounded-md border"
          >
            {croppedUrl != null && !thumbnailBroken ? (
              <img
                src={croppedUrl}
                alt={`Document ${analysis.position}`}
                loading="lazy"
                className="size-full object-cover"
                onError={() => setThumbnailBroken(true)}
              />
            ) : (
              <span className="text-ink-muted grid size-full place-items-center">
                <FileText className="size-5" strokeWidth={1.5} />
              </span>
            )}
          </a>
        )}
        <div className="min-w-0 flex-1">
          {count > 1 && (
            <p className="text-sm font-medium">
              Document {analysis.position} of {count}
            </p>
          )}
          <div className="flex items-center">
            <p className="text-ink-muted text-xs">
              {analysis.classification
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
                  setClassification(
                    analysis.classification ??
                      CASHOUT_DOCUMENT_CLASSIFICATIONS[0]!,
                  );
                  setClassifyOpen(true);
                }}
              >
                <Pencil className="size-3" />
              </Button>
            )}
          </div>
        </div>
        <AnalysisStatusBadge status={analysis.status} />
      </div>

      {analysis.status === "extracting" && (
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

      {analysis.status === "failed" && (
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
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                variant="outline"
                onClick={() => retry.mutate()}
                loading={retry.isPending}
              >
                <RefreshCw className="size-4" />
                Retry extraction
              </Button>
              <Button
                variant="outline"
                onClick={replaceImage.open}
                loading={replaceImage.pending}
              >
                <Upload className="size-4" />
                Replace image
              </Button>
              <Button variant="outline" onClick={() => setManualOpen(true)}>
                <Pencil className="size-4" />
                Enter details manually
              </Button>
            </div>
          )}
          <ErrorBanner error={retry.error} />
        </div>
      )}

      {analysis.status === "needs_verification" && (
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

      {analysis.status === "verified" && (
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
            {analysis.provider == null
              ? "Entered manually — verified"
              : "Verified"}{" "}
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
    </div>
  );
}

/** The analyses in the reading order the documents were found in. */
function inPositionOrder(
  analyses: CashoutDocumentAnalysis[],
): CashoutDocumentAnalysis[] {
  return [...analyses].sort((a, b) => a.position - b.position);
}

function croppedUrlOf(
  analysis: CashoutDocumentAnalysis | undefined,
): string | null {
  return analysis?.croppedContentType != null
    ? cashoutApi.analysisCroppedUrl(analysis.id)
    : null;
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
