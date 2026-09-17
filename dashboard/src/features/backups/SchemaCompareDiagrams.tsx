import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import { useQuery } from "@tanstack/react-query";
import { api, qk } from "../../api/endpoints";
import type { SchemaDiff, SourceSchema } from "../../api/types";
import { PageSpinner } from "../../components/ui/Spinner";
import { EmptyState, ErrorState } from "../../components/ui/States";
import { useTheme } from "../../lib/theme";
import { EntityNode } from "../schema/EntityNode";
import { ENTITY_HANDLE, type EntityFlowNode, type RelationFlowEdge } from "../schema/flow-types";
import { buildGraph, chooseSides, handleId } from "../schema/graph";
import { autoLayout } from "../schema/layout";
import { RelationEdge } from "../schema/RelationEdge";

const nodeTypes: NodeTypes = { entity: EntityNode };
const edgeTypes: EdgeTypes = { relation: RelationEdge };

export type CompareSide = { backupId: string | "current"; label: string };

/** Two read-only ERDs side by side (lazy-loaded; React Flow is heavy). Changed entities are highlighted. */
export default function SchemaCompareDiagrams({
  projectId,
  sourceId,
  from,
  to,
  diff,
}: {
  projectId: string;
  sourceId: string;
  from: CompareSide;
  to: CompareSide;
  diff: SchemaDiff | undefined;
}) {
  const fromChanged = new Set(diff?.entities.filter((e) => e.change !== "added").map((e) => e.name) ?? []);
  const toChanged = new Set(diff?.entities.filter((e) => e.change !== "removed").map((e) => e.name) ?? []);
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <DiagramPane projectId={projectId} sourceId={sourceId} side={from} highlight={fromChanged} />
      <DiagramPane projectId={projectId} sourceId={sourceId} side={to} highlight={toChanged} />
    </div>
  );
}

function DiagramPane({
  projectId,
  sourceId,
  side,
  highlight,
}: {
  projectId: string;
  sourceId: string;
  side: CompareSide;
  highlight: Set<string>;
}) {
  const schema = useQuery({
    queryKey:
      side.backupId === "current"
        ? ["projects", projectId, "schema", "source", sourceId]
        : qk.backupSchema(projectId, sourceId, side.backupId),
    queryFn: async (): Promise<SourceSchema | null> => {
      if (side.backupId === "current") {
        const full = await api.schema.get(projectId, { source_id: sourceId });
        return full.sources.find((s) => s.source_id === sourceId) ?? full.sources[0] ?? null;
      }
      return api.backups.schema(projectId, sourceId, side.backupId);
    },
    staleTime: 60_000,
  });
  return (
    <section className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-border">
      <header className="border-b border-border bg-surface-2/60 px-3 py-2 text-sm font-semibold">{side.label}</header>
      <div className="h-[46dvh] min-h-[320px]">
        {schema.isPending ? (
          <PageSpinner label="Loading schema…" />
        ) : schema.isError ? (
          <ErrorState className="m-3 border-0" error={schema.error} onRetry={() => void schema.refetch()} />
        ) : !schema.data || schema.data.entities.length === 0 ? (
          <div className="flex h-full items-center justify-center p-4">
            <EmptyState className="border-0" title="Empty schema" description="No tables or collections in this version." />
          </div>
        ) : (
          <ReactFlowProvider>
            <ReadOnlyErd source={schema.data} highlight={highlight} />
          </ReactFlowProvider>
        )}
      </div>
    </section>
  );
}

function ReadOnlyErd({ source, highlight }: { source: SourceSchema; highlight: Set<string> }) {
  const { resolved } = useTheme();
  const graph = useMemo(() => {
    const schema = { sources: [source], links: [], conventions: [], generated_at: "" };
    return buildGraph(schema, new Set([source.source_id]));
  }, [source]);
  const positions = useMemo(() => autoLayout(graph), [graph]);

  const nodes: EntityFlowNode[] = graph.nodes.map((n) => ({
    id: n.id,
    type: "entity",
    position: positions[n.id] ?? { x: 0, y: 0 },
    draggable: false,
    data: {
      source: { source_id: n.source.source_id, name: n.source.name, kind: n.source.kind, engine: n.source.engine },
      entity: n.entity,
      issueCount: 0,
      issueFields: [],
      highlight: highlight.has(n.entity.name),
      dimmed: false,
      focusField: null,
    },
  }));
  const nodeById = new Map(graph.nodes.map((n) => [n.id, n]));
  const edges: RelationFlowEdge[] = graph.edges.map((e) => {
    const { fromSide, toSide } = chooseSides(
      positions[e.from.nodeId] ?? { x: 0, y: 0 },
      positions[e.to.nodeId] ?? { x: 0, y: 0 },
      e.from.nodeId === e.to.nodeId,
    );
    const fromHas = nodeById.get(e.from.nodeId)?.entity.fields.some((f) => f.name === e.from.field);
    const toHas = nodeById.get(e.to.nodeId)?.entity.fields.some((f) => f.name === e.to.field);
    return {
      id: e.id,
      type: "relation",
      source: e.from.nodeId,
      target: e.to.nodeId,
      sourceHandle: handleId(fromHas ? e.from.field : ENTITY_HANDLE, fromSide),
      targetHandle: handleId(toHas ? e.to.field : ENTITY_HANDLE, toSide),
      data: { info: e, highlighted: false, dimmed: false },
    };
  });

  return (
    <ReactFlow<EntityFlowNode, RelationFlowEdge>
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      colorMode={resolved}
      fitView
      fitViewOptions={{ padding: 0.15 }}
      minZoom={0.1}
      maxZoom={2}
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--border-strong)" />
      <Controls showInteractive={false} position="bottom-left" />
    </ReactFlow>
  );
}
