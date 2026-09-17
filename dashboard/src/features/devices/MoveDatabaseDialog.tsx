import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import { usePlacementOptions } from "../../api/hooks";
import type { DataSource } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { JobProgressPanel } from "../jobs/JobProgress";
import { deviceIdFromValue, engineForKind, placementDisplay, placementValue } from "./eligibility";
import { HostOnSelect } from "./HostOnSelect";

export function MoveDatabaseDialog({
  projectId,
  source,
  onClose,
}: {
  projectId: string;
  source: DataSource;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const options = usePlacementOptions(projectId);
  const engine = engineForKind(source.kind);
  const current = placementValue(source.device_id);
  const [choice, setChoice] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const targets = (options.data ?? []).map((o) => placementDisplay(o, engine)).filter((d) => d.value !== current);
  const target = targets.find((d) => d.value === choice && !d.disabled) ?? targets.find((d) => !d.disabled) ?? null;

  const move = useMutation({
    mutationFn: () => api.dataSources.move(projectId, source.id, deviceIdFromValue(target?.value ?? "")),
    onSuccess: ({ job }) => {
      setJobId(job.id);
      void queryClient.invalidateQueries({ queryKey: qk.jobs(projectId) });
    },
  });

  const targetName = options.data?.find((o) => placementValue(o.device_id) === target?.value)?.name ?? "the new host";

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Move ${source.name}`}
      description="Copy this database to another host and switch the project over to it."
      dismissible={!move.isPending}
      footer={
        jobId ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <>
            <Button onClick={onClose} disabled={move.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              icon={<ArrowRightLeft className="size-4" />}
              loading={move.isPending}
              disabled={!target}
              onClick={() => move.mutate()}
            >
              Move database
            </Button>
          </>
        )
      }
    >
      {jobId ? (
        <JobProgressPanel
          projectId={projectId}
          jobId={jobId}
          title={`Moving to ${targetName}`}
          onFinished={(job) => {
            void queryClient.invalidateQueries({ queryKey: qk.dataSources(projectId) });
            void queryClient.invalidateQueries({ queryKey: qk.placement(projectId) });
            if (job.status === "succeeded") toast.success(`${source.name} moved.`);
            else if (job.status === "failed") toast.error(job.error ?? "The move failed.", "Move failed");
          }}
          result={() => (
            <p className="text-sm text-fg/80">
              The project now uses the new copy. The old copy is kept for 7 days in case you need to go back.
            </p>
          )}
        />
      ) : (
        <div className="space-y-4">
          <HostOnSelect
            label="Move to"
            options={options.data}
            engine={engine}
            value={target?.value ?? ""}
            onChange={setChoice}
            loading={options.isPending}
            error={options.error}
            excludeDeviceId={current}
          />
          {options.data && targets.length === 0 && (
            <Alert tone="info">
              There's nowhere else to move this database. Attach another PC as a host device in Settings → Devices.
            </Alert>
          )}
          <Alert tone="warning" title="What happens">
            Deployer takes a safety version, restores it on the new host, briefly pauses writes while it switches the
            project over, and keeps the old copy for 7 days. Apps using the connection details may need the new host
            name afterwards.
          </Alert>
          {move.error && <ErrorAlert error={move.error} />}
        </div>
      )}
    </Dialog>
  );
}
