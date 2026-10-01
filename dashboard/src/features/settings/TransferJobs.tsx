import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, History } from "lucide-react";
import { errorMessage, saveBlob } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { isJobFinished } from "../../api/hooks";
import type { ImportJobResult, Job } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ProgressBar } from "../../components/ui/Progress";
import { PageSpinner } from "../../components/ui/Spinner";
import { Card, EmptyState, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { relativeTime } from "../../lib/format";
import { JobStatusBadge } from "../jobs/JobProgress";
import { jobLabel } from "../jobs/jobs";
import { ImportSummaryList } from "./ImportSummaryList";

/** Downloads a finished export (kept on the server for 24 hours). */
export function DownloadExportButton({ jobId }: { jobId: string }) {
  const toast = useToast();
  const download = useMutation({
    mutationFn: () => api.transfers.download(jobId),
    onSuccess: (file) => saveBlob(file),
    onError: (e) => toast.error(errorMessage(e), "Download failed"),
  });
  return (
    <Button size="sm" variant="primary" icon={<Download className="size-4" />} loading={download.isPending} onClick={() => download.mutate()}>
      Download
    </Button>
  );
}

/** The signed-in user's exports and imports (GET /transfers), polled while one runs. */
function useTransfers() {
  return useQuery({
    queryKey: qk.transfers,
    queryFn: api.transfers.list,
    refetchInterval: (query) => (query.state.data?.some((j) => !isJobFinished(j.status)) ? 1500 : false),
  });
}

export function RecentTransfers() {
  const transfers = useTransfers();
  const queryClient = useQueryClient();
  const toast = useToast();
  // Jobs already finished when the page opened; any other job that finishes gets a toast.
  const settled = useRef<Set<string> | null>(null);

  useEffect(() => {
    if (!transfers.data) return;
    const first = settled.current === null;
    const seen = (settled.current ??= new Set());
    for (const job of transfers.data) {
      if (!isJobFinished(job.status) || seen.has(job.id)) continue;
      seen.add(job.id);
      if (first || job.status !== "succeeded") continue;
      if (job.type === "transfer.import") {
        void queryClient.invalidateQueries({ queryKey: qk.projects });
        toast.success("Import finished.");
      } else {
        toast.success("Export ready to download.");
      }
    }
  }, [transfers.data, queryClient, toast]);

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <History className="size-4 text-accent" /> Recent exports &amp; imports
        </span>
      }
      description="They run in the background, so you can leave this page. Export files are kept for 24 hours."
    >
      {transfers.isPending ? (
        <PageSpinner />
      ) : transfers.isError ? (
        <ErrorState error={transfers.error} onRetry={() => void transfers.refetch()} />
      ) : transfers.data.length === 0 ? (
        <EmptyState title="Nothing yet" description="Exports and imports you start show up here." />
      ) : (
        <ul className="divide-y divide-border">
          {transfers.data.map((job) => (
            <li key={job.id} className="py-3 first:pt-0 last:pb-0">
              <TransferRow job={job} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TransferRow({ job }: { job: Job }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.transfers.cancel(job.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: qk.transfers }),
    onError: (e) => toast.error(errorMessage(e), "Couldn't cancel"),
  });
  const active = !isJobFinished(job.status);
  const imported = job.type === "transfer.import" && job.status === "succeeded" ? (job.result as ImportJobResult) : null;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{jobLabel(job.type)}</span>
        <JobStatusBadge status={job.status} />
        {job.type === "transfer.export" && job.status === "succeeded" && <DownloadExportButton jobId={job.id} />}
        {/* An import can't stop halfway; only an export checks for cancel (before each database). */}
        {active && (job.type === "transfer.export" || job.status === "queued") && (
          <Button size="sm" variant="ghost" loading={cancel.isPending} onClick={() => cancel.mutate()}>
            Cancel
          </Button>
        )}
      </div>
      {active && <ProgressBar value={job.status === "queued" ? null : job.progress * 100} label={`${jobLabel(job.type)} progress`} />}
      <p className="text-xs text-muted" title={job.created_at}>
        Started {relativeTime(job.started_at ?? job.created_at)}
        {active && job.message ? ` · ${job.message}` : ""}
      </p>
      {job.error && <p className="text-xs break-words text-danger">{job.error}</p>}
      {imported && (
        <div className="space-y-2">
          <ImportSummaryList summary={imported.summary} />
          <ul className="space-y-1 text-sm">
            {imported.projects.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${p.id}`} className="font-medium text-accent hover:underline">
                  {p.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
