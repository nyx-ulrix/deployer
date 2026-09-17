import { useState } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import { isJobFinished, useDataSources } from "../../api/hooks";
import type { Job, Project } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { PageSpinner } from "../../components/ui/Spinner";
import { EmptyState, ErrorState } from "../../components/ui/States";
import { hasRole } from "../../lib/roles";
import { localTimeZone } from "../../lib/format";
import { JobRow } from "./JobProgress";

/** "Activity" button for the project header plus the jobs drawer it opens. */
export function JobsButton({ project }: { project: Project }) {
  const [open, setOpen] = useState(false);
  const jobs = useQuery({
    queryKey: qk.jobs(project.id),
    queryFn: () => api.jobs.list(project.id),
    refetchInterval: (query) => {
      if (open) return 3000;
      return query.state.data?.some((j) => !isJobFinished(j.status)) ? 5000 : 60_000;
    },
    retry: false,
  });
  const active = jobs.data?.filter((j) => !isJobFinished(j.status)).length ?? 0;

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        icon={<Activity className="size-4" />}
        onClick={() => setOpen(true)}
        aria-label={active ? `Activity, ${active} running` : "Activity"}
      >
        <span className="hidden sm:inline">Activity</span>
        {active > 0 && <Badge tone="info">{active}</Badge>}
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        placement="right"
        title="Activity"
        description={`Backups, restores and moves for ${project.name}. Times in ${localTimeZone()}.`}
        footer={<Button onClick={() => setOpen(false)}>Close</Button>}
      >
        <JobsList project={project} query={jobs} />
      </Dialog>
    </>
  );
}

function JobsList({
  project,
  query,
}: {
  project: Project;
  query: UseQueryResult<Job[]>;
}) {
  const sources = useDataSources(project.id);
  if (query.isPending) return <PageSpinner />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (query.data.length === 0) {
    return (
      <EmptyState
        icon={<Activity className="size-5" />}
        title="No activity yet"
        description="Versions, restores and database moves show up here while they run."
      />
    );
  }
  const nameOf = (id: string | null) => (id ? sources.data?.find((s) => s.id === id)?.name : undefined);
  return (
    <ul className="divide-y divide-border">
      {query.data.map((job) => (
        <li key={job.id} className="py-3 first:pt-0 last:pb-0">
          {nameOf(job.data_source_id) && <p className="mb-1 text-xs text-muted">{nameOf(job.data_source_id)}</p>}
          <JobRow job={job} projectId={project.id} canCancel={hasRole(project.my_role, "admin")} />
        </li>
      ))}
    </ul>
  );
}
