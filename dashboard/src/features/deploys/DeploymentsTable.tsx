import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { Deployment, DeploymentStatus } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Table, TBody, Td, Th, THead, Tr } from "../../components/ui/Table";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { formatDuration, relativeTime } from "../../lib/format";
import { canRollback, DEPLOYMENT_STATUS, deploymentDuration, isActive, shortSha, TRIGGER_LABELS } from "./deploys";

export function DeploymentStatusBadge({ status }: { status: DeploymentStatus }) {
  const s = DEPLOYMENT_STATUS[status];
  return (
    <Badge tone={s.tone}>
      {isActive(status) && <Loader2 className="size-3 animate-spin" />}
      {s.label}
    </Badge>
  );
}

export function DeploymentsTable({
  projectId,
  appId,
  deployments,
  selectedId,
  onSelect,
  canDeploy,
}: {
  projectId: string;
  appId: string;
  deployments: Deployment[];
  selectedId: string | null;
  onSelect: (d: Deployment) => void;
  canDeploy: boolean;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [rollingBack, setRollingBack] = useState<Deployment | null>(null);
  const rollback = useMutation({
    mutationFn: (d: Deployment) => api.apps.rollback(projectId, appId, d.id),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: qk.deployments(projectId, appId) });
      setRollingBack(null);
      onSelect(created);
      toast.success("Rollback queued.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't roll back"),
  });

  return (
    <>
      <Table>
        <THead>
          <Tr>
            <Th>Status</Th>
            <Th className="hidden sm:table-cell">Trigger</Th>
            <Th>Commit</Th>
            <Th>When</Th>
            <Th className="hidden sm:table-cell">Duration</Th>
            <Th>
              <span className="sr-only">Actions</span>
            </Th>
          </Tr>
        </THead>
        <TBody>
          {deployments.map((d) => (
            <Tr
              key={d.id}
              onClick={() => onSelect(d)}
              className={cn("cursor-pointer hover:bg-surface-2", d.id === selectedId && "bg-accent-soft/40")}
              aria-selected={d.id === selectedId}
            >
              <Td>
                <DeploymentStatusBadge status={d.status} />
              </Td>
              <Td className="hidden text-muted sm:table-cell">{TRIGGER_LABELS[d.trigger]}</Td>
              <Td className="max-w-64">
                <span className="font-mono text-xs">{shortSha(d.commit_sha)}</span>
                {d.commit_message && <span className="ml-2 truncate text-xs text-muted" title={d.commit_message}>{d.commit_message}</span>}
                {d.rollback_of && <span className="ml-2 text-xs text-muted">(rollback)</span>}
              </Td>
              <Td className="whitespace-nowrap text-muted" title={d.created_at}>
                {relativeTime(d.created_at)}
              </Td>
              <Td className="hidden whitespace-nowrap text-muted sm:table-cell">{formatDuration(deploymentDuration(d))}</Td>
              <Td className="text-right">
                {canDeploy && canRollback(d) && (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<RotateCcw className="size-3.5" />}
                    onClick={(e) => {
                      e.stopPropagation();
                      setRollingBack(d);
                    }}
                  >
                    Rollback
                  </Button>
                )}
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
      {rollingBack && (
        <ConfirmDialog
          open
          onClose={() => setRollingBack(null)}
          onConfirm={() => rollback.mutate(rollingBack)}
          loading={rollback.isPending}
          destructive={false}
          title={`Roll back to ${shortSha(rollingBack.commit_sha)}?`}
          description="The old image is started as a new deployment without rebuilding; the current one is swapped out once it answers."
          confirmLabel="Roll back"
        />
      )}
    </>
  );
}
