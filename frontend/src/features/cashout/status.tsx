import type {
  CashoutSubmissionStatus,
  DocumentAnalysisStatus,
} from "@/api/types";
import { Badge } from "@/components/ui";
import { enumLabel } from "@/lib/format";

export function SubmissionStatusBadge({
  status,
}: {
  status: CashoutSubmissionStatus;
}) {
  return (
    <Badge tone={status === "completed" ? "success" : "info"}>
      {status === "processing" ? "In progress" : enumLabel(status)}
    </Badge>
  );
}

const ANALYSIS_TONES = {
  extracting: "info",
  needs_verification: "warning",
  verified: "success",
  failed: "danger",
} as const;

export function AnalysisStatusBadge({
  status,
}: {
  status: DocumentAnalysisStatus;
}) {
  return <Badge tone={ANALYSIS_TONES[status]}>{enumLabel(status)}</Badge>;
}
