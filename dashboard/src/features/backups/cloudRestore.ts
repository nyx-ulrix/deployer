import type { CloudRestoredFrom } from "../../api/types";
import { formatDateTime } from "../../lib/format";

/** One plain sentence on where a restored DynamoDB table came from (docs/CLOUD.md "C2-2"). */
export function restoredFrom(r: CloudRestoredFrom): string {
  const of = r.source_name ? `${r.table} (${r.source_name})` : r.table;
  if (r.kind === "backup") return `Restored from the backup ${r.backup ?? "?"} of ${of}`;
  return `Restored from ${of} as it was ${r.latest ? "when the restore started" : `at ${formatDateTime(r.time)}`}`;
}
