import type { JobStatus } from "../../api/types";
import type { BadgeTone } from "../../components/ui/Badge";

const TYPE_LABELS: [RegExp, string][] = [
  [/restore_deleted|deleted.*restore/, "Restore deleted database"],
  [/restore/, "Restore"],
  [/verify/, "Verify version"],
  [/copy/, "Copy backup"],
  [/move/, "Move database"],
  [/prune/, "Prune old versions"],
  [/log|binlog|oplog/, "Archive recovery logs"],
  [/platform/, "Platform backup"],
  [/snapshot|backup/, "Create version"],
];

export function jobLabel(type: string): string {
  for (const [re, label] of TYPE_LABELS) if (re.test(type)) return label;
  return type.replace(/[._]/g, " ");
}

export const JOB_STATUS: Record<JobStatus, { label: string; tone: BadgeTone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  succeeded: { label: "Succeeded", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};
