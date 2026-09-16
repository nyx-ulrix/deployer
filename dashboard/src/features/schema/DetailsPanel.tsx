import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MousePointerClick, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { ConventionIssue } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { engineLabel, formatNumber } from "../../lib/format";
import { MARKER_LABEL } from "./crowsfoot";
import type { GraphEdgeInfo, GraphNodeInfo } from "./graph";

export function DetailsPanel({
  node,
  edge,
  edges,
  projectId,
  canEditLinks,
  onFocusNode,
  onLinkDeleted,
}: {
  node: GraphNodeInfo | null;
  edge: GraphEdgeInfo | null;
  edges: GraphEdgeInfo[];
  projectId: string;
  canEditLinks: boolean;
  onFocusNode: (nodeId: string, field?: string | null) => void;
  onLinkDeleted: () => void;
}) {
  if (edge) {
    return (
      <EdgeDetails
        edge={edge}
        projectId={projectId}
        canEditLinks={canEditLinks}
        onFocusNode={onFocusNode}
        onLinkDeleted={onLinkDeleted}
      />
    );
  }
  if (node) return <EntityDetails node={node} edges={edges} onFocusNode={onFocusNode} />;
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-muted">
      <MousePointerClick className="size-6" />
      <p>Click an entity or a relationship line to see its details.</p>
    </div>
  );
}

const KIND_LABEL = { fk: "Foreign key", inferred: "Inferred relationship", link: "Cross-database link" } as const;

function EdgeDetails({
  edge,
  projectId,
  canEditLinks,
  onFocusNode,
  onLinkDeleted,
}: {
  edge: GraphEdgeInfo;
  projectId: string;
  canEditLinks: boolean;
  onFocusNode: (nodeId: string, field?: string | null) => void;
  onLinkDeleted: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.schema.deleteLink(projectId, edge.linkId ?? ""),
    onSuccess: () => {
      setConfirming(false);
      void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
      toast.success("Link deleted.");
      onLinkDeleted();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete link"),
  });

  const end = (label: string, ref: GraphEdgeInfo["from"], marker: keyof typeof MARKER_LABEL) => (
    <div className="rounded-lg border border-border p-2">
      <div className="text-[11px] text-muted uppercase">{label}</div>
      <button
        type="button"
        className="mt-0.5 block max-w-full truncate font-mono text-sm font-medium hover:text-accent"
        onClick={() => onFocusNode(ref.nodeId, ref.field)}
      >
        {ref.entity}.{ref.field}
      </button>
      <div className="text-xs text-muted">{MARKER_LABEL[marker]}</div>
    </div>
  );

  return (
    <div className="space-y-3 p-3 text-sm">
      <div className="flex items-center gap-2">
        <Badge tone={edge.kind === "link" ? "link" : edge.kind === "fk" ? "sql" : "neutral"}>{KIND_LABEL[edge.kind]}</Badge>
        <span className="font-mono text-xs text-muted">{edge.cardinality.replaceAll("_", " ")}</span>
      </div>
      {end("From", edge.from, edge.ends.source)}
      {end("To", edge.to, edge.ends.target)}
      {edge.note && <p className="rounded-lg bg-surface-2 p-2 text-sm">{edge.note}</p>}
      {edge.kind === "inferred" && (
        <p className="text-xs text-muted">
          Inferred from naming or sampled references. Declare a foreign key (SQL) or add an index to make it explicit.
        </p>
      )}
      {edge.kind === "link" && canEditLinks && (
        <Button variant="outline-danger" size="sm" icon={<Trash2 className="size-3.5" />} onClick={() => setConfirming(true)}>
          Delete link
        </Button>
      )}
      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={() => remove.mutate()}
        loading={remove.isPending}
        title="Delete this link?"
        description={`${edge.from.entity}.${edge.from.field} → ${edge.to.entity}.${edge.to.field} will be removed from the diagram and exports. No data is changed.`}
        confirmLabel="Delete link"
      />
    </div>
  );
}

function IssueList({ issues }: { issues: ConventionIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <section>
      <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Conventions</h4>
      <ul className="space-y-1">
        {issues.map((i, idx) => (
          <li key={idx} className="flex gap-2 text-xs">
            <span
              className={cn(
                "h-fit rounded px-1 font-mono font-bold",
                i.severity === "warning" ? "bg-warning-soft text-warning" : "bg-info-soft text-info",
              )}
            >
              {i.rule}
            </span>
            <span>
              {i.field && <code className="font-mono">{i.field}: </code>}
              {i.message}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EntityDetails({
  node,
  edges,
  onFocusNode,
}: {
  node: GraphNodeInfo;
  edges: GraphEdgeInfo[];
  onFocusNode: (nodeId: string, field?: string | null) => void;
}) {
  const { entity, source } = node;
  const related = edges.filter((e) => e.from.nodeId === node.id || e.to.nodeId === node.id);
  return (
    <div className="space-y-4 p-3 text-sm">
      <div>
        <h3 className="font-mono text-base font-semibold break-all">{entity.name}</h3>
        <div className="mt-1 flex flex-wrap gap-1">
          <Badge tone={source.kind === "sql" ? "sql" : "nosql"}>{engineLabel(source.engine)}</Badge>
          <Badge>{source.name}</Badge>
          <Badge>{entity.type}</Badge>
          {entity.row_count !== null && (
            <Badge>
              {formatNumber(entity.row_count)} {source.kind === "sql" ? "rows" : "documents"}
            </Badge>
          )}
        </div>
      </div>

      <section>
        <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">
          {source.kind === "sql" ? "Columns" : "Fields"} ({entity.fields.length})
        </h4>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-xs">
            <tbody className="divide-y divide-border">
              {entity.fields.map((f) => (
                <tr key={f.name}>
                  <td className="px-2 py-1 font-mono font-medium">{f.name}</td>
                  <td className="px-2 py-1 font-mono text-muted">{f.data_type}</td>
                  <td className="px-2 py-1 text-right whitespace-nowrap text-muted">
                    {[
                      f.primary_key && "PK",
                      f.foreign_key && `FK→${f.foreign_key.entity}`,
                      f.unique && !f.primary_key && "UQ",
                      !f.nullable && !f.primary_key && "NN",
                      f.indexed && !f.unique && !f.primary_key && "IDX",
                      f.occurrence !== null && f.occurrence < 1 && `${Math.round(f.occurrence * 100)}%`,
                      f.default !== null && `= ${f.default}`,
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {entity.indexes.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Indexes</h4>
          <ul className="space-y-0.5 text-xs">
            {entity.indexes.map((ix) => (
              <li key={ix.name} className="font-mono">
                {ix.name} ({ix.fields.join(", ")}){ix.unique && <span className="text-accent"> unique</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {related.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Relationships</h4>
          <ul className="space-y-1 text-xs">
            {related.map((e) => {
              const outgoing = e.from.nodeId === node.id;
              const other = outgoing ? e.to : e.from;
              return (
                <li key={e.id}>
                  <button
                    type="button"
                    className="text-left font-mono hover:text-accent"
                    onClick={() => onFocusNode(other.nodeId, other.field)}
                  >
                    {outgoing
                      ? `${e.from.field} → ${e.to.entity}.${e.to.field}`
                      : `${e.from.entity}.${e.from.field} → ${e.to.field}`}
                  </button>
                  <span className={cn("ml-1", e.kind === "link" ? "text-link" : "text-muted")}>
                    ({e.kind === "fk" ? "FK" : e.kind})
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <IssueList issues={node.issues} />

      {entity.validator && (
        <section>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Validator</h4>
          <pre className="max-h-60 overflow-auto rounded-lg bg-surface-2 p-2 font-mono text-[11px]">
            {JSON.stringify(entity.validator, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );
}
