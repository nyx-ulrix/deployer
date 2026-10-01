import type { JobStatus } from "../../api/types";
import type { BadgeTone } from "../../components/ui/Badge";

/** Every job type the API creates (A-087). api/tests/test_job_labels.py keeps this in step with the API. */
export const JOB_LABELS: Record<string, string> = {
  "backup.snapshot": "Create version",
  "backup.restore": "Restore version",
  "backup.verify": "Verify version",
  "backup.prune": "Prune old versions",
  "backup.copy": "Copy versions to backup storage",
  "backup.archive_logs": "Archive recovery logs",
  "backup.platform_snapshot": "Platform backup",
  "schema.drop": "Drop table or collection",
  "source.finalize_delete": "Delete database",
  "source.undelete": "Restore deleted database",
  "device.move": "Move database",
  "replica.copy": "Copy database to device",
  "app.deploy": "Deploy app",
  "app.route": "Update app routing",
  "app.remove": "Remove app",
  "app.replicate": "Deploy app to device",
  "app.cloud_teardown": "Remove cloud deployment",
  "app.cloud_domain": "Check custom domain",
  "data_source.cloud_create": "Create database in AWS",
  "data_source.cloud_delete": "Delete database in AWS",
  "transfer.export": "Export",
  "transfer.import": "Import projects",
};

export function jobLabel(type: string): string {
  return JOB_LABELS[type] ?? "Background task";
}

export const JOB_STATUS: Record<JobStatus, { label: string; tone: BadgeTone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  succeeded: { label: "Succeeded", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};
