import { useEffect, useRef, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleSlash, Loader2, XCircle } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { isJobFinished, useJob } from "../../api/hooks";
import type { Job, JobStatus } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ProgressBar } from "../../components/ui/Progress";
import { ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { relativeTime } from "../../lib/format";
import { JOB_STATUS, jobLabel } from "./jobs";

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const s = JOB_STATUS[status];
  return (
    <Badge tone={s.tone}>
      {status === "running" && <Loader2 className="size-3 animate-spin" />}
      {s.label}
    </Badge>
  );
}

/** Progress row for a job already loaded (used by the activity drawer). */
export function JobRow({ job, projectId, canCancel }: { job: Job; projectId: string; canCancel: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.jobs.cancel(projectId, job.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs(projectId) });
      toast.info("Cancellation requested.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't cancel job"),
  });
  const active = !isJobFinished(job.status);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{jobLabel(job.type)}</span>
        <JobStatusBadge status={job.status} />
      </div>
      {active && (
        <ProgressBar
          value={job.status === "queued" ? null : job.progress * 100}
          label={`${jobLabel(job.type)} progress`}
        />
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <span title={job.created_at}>Started {relativeTime(job.started_at ?? job.created_at)}</span>
        {job.finished_at && <span>Finished {relativeTime(job.finished_at)}</span>}
        {active && job.status === "running" && <span>{Math.round(job.progress * 100)}%</span>}
        {active && canCancel && (
          <Button size="sm" variant="ghost" className="ml-auto h-6 px-2" loading={cancel.isPending} onClick={() => cancel.mutate()}>
            Cancel
          </Button>
        )}
      </div>
      {job.message && active && <p className="text-xs text-fg/80">{job.message}</p>}
      {job.error && <p className="text-xs break-words text-danger">{job.error}</p>}
    </div>
  );
}

/**
 * Live progress panel for one job (polls GET /jobs/{id} every 1.5 s). Calls `onFinished` once when the
 * job reaches a final state and renders `result(job)` on success.
 */
export function JobProgressPanel({
  projectId,
  jobId,
  title,
  onFinished,
  result,
  className,
}: {
  projectId: string;
  jobId: string;
  title: string;
  onFinished?: (job: Job) => void;
  result?: (job: Job) => ReactNode;
  className?: string;
}) {
  const job = useJob(projectId, jobId);
  const notified = useRef(false);
  const onFinishedRef = useRef(onFinished);
  useEffect(() => {
    onFinishedRef.current = onFinished;
  });
  useEffect(() => {
    if (job.data && isJobFinished(job.data.status) && !notified.current) {
      notified.current = true;
      onFinishedRef.current?.(job.data);
    }
  }, [job.data]);

  if (job.isError) return <ErrorAlert error={job.error} className={className} />;
  const data = job.data;
  const status: JobStatus = data?.status ?? "queued";
  const Icon =
    status === "succeeded" ? CheckCircle2 : status === "failed" ? XCircle : status === "cancelled" ? CircleSlash : Loader2;
  return (
    <div
      className={cn(
        "rounded-xl border border-border p-4",
        status === "succeeded" && "bg-success-soft/40",
        status === "failed" && "bg-danger-soft/40",
        className,
      )}
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <Icon
          className={cn(
            "mt-0.5 size-5 shrink-0",
            status === "succeeded" && "text-success",
            status === "failed" && "text-danger",
            status === "cancelled" && "text-muted",
            !isJobFinished(status) && "animate-spin text-accent",
          )}
        />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{title}</p>
            <JobStatusBadge status={status} />
          </div>
          {!isJobFinished(status) && (
            <>
              <ProgressBar value={status === "running" && data ? data.progress * 100 : null} label={`${title} progress`} />
              <p className="text-xs text-muted">
                {data?.message ?? (status === "queued" ? "Waiting for the worker…" : "Working…")}
                {status === "running" && data ? ` · ${Math.round(data.progress * 100)}%` : ""}
              </p>
            </>
          )}
          {status === "failed" && <p className="text-sm break-words text-danger">{data?.error ?? "The job failed."}</p>}
          {status === "cancelled" && <p className="text-sm text-muted">The job was cancelled.</p>}
          {status === "succeeded" && data && result?.(data)}
        </div>
      </div>
    </div>
  );
}
