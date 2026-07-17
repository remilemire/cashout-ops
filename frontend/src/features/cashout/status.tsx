// frontend/src/features/cashout/status.tsx

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
    <Badge tone={status === "COMPLETED" ? "success" : "info"}>
      {status === "PROCESSING" ? "In progress" : enumLabel(status)}
    </Badge>
  );
}

const ANALYSIS_TONES = {
  EXTRACTING: "info",
  NEEDS_VERIFICATION: "warning",
  VERIFIED: "success",
  FAILED: "danger",
} as const;

export function AnalysisStatusBadge({
  status,
}: {
  status: DocumentAnalysisStatus;
}) {
  return <Badge tone={ANALYSIS_TONES[status]}>{enumLabel(status)}</Badge>;
}
