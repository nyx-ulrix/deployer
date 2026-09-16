import { useCallback, useMemo, useState, type KeyboardEvent } from "react";
import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type EdgeTypes,
  type NodeChange,
  type NodeTypes,
} from "@xyflow/react";
import {
  BookOpen,
  ChevronDown,
  Database,
  Download,
  Filter,
  LayoutGrid,
  Link2,
  ListChecks,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  SquareMousePointer,
} from "lucide-react";
import { errorMessage, saveBlob } from "../../api/client";
import { api } from "../../api/endpoints";
import { useSchema } from "../../api/hooks";
import type { ConventionIssue, ProjectSchema, SchemaExportFormat } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Checkbox } from "../../components/ui/Input";
import { Menu, MenuItem } from "../../components/ui/Menu";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { Tabs } from "../../components/ui/Tabs";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { engineLabel, relativeTime } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { useProjectContext } from "../projects/project-context";
import { AddLinkDialog } from "./AddLinkDialog";
import { ConventionsPanel } from "./ConventionsPanel";
import { DetailsPanel } from "./DetailsPanel";
import { EntityNode, SourceGroupNode } from "./EntityNode";
import {
  ENTITY_HANDLE,
  type EntityFlowNode,
  type RelationFlowEdge,
  type SchemaFlowNode,
  type SourceGroupFlowNode,
} from "./flow-types";
import { buildGraph, chooseSides, estimateHeight, handleId, NODE_WIDTH, nodeIdFor, type XY } from "./graph";
import { autoLayout, GROUP_PAD, loadPositions, savePositions } from "./layout";
import { Legend } from "./Legend";
import { RelationEdge } from "./RelationEdge";

const nodeTypes: NodeTypes = { entity: EntityNode, sourceGroup: SourceGroupNode };
const edgeTypes: EdgeTypes = { relation: RelationEdge };

type PanelTab = "conventions" | "details" | "legend";

export default function SchemaTab() {
  const { project, can } = useProjectContext();
  const schema = useSchema(project.id);

  if (schema.isPending) return <PageSpinner label="Reading schema…" />;
  if (schema.isError) return <ErrorState error={schema.error} onRetry={() => void schema.refetch()} />;
  if (schema.data.sources.length === 0) {
    return (
      <EmptyState
        icon={<Database className="size-5" />}
        title="No databases to diagram"
        description="Add a SQL or NoSQL database on the Databases tab and its tables and collections will appear here."
      />
    );
  }

  return (
    <ReactFlowProvider>
      <SchemaViewer
        projectId={project.id}
        schema={schema.data}
        canEditLinks={can("developer")}
        refreshing={schema.isFetching}
        onRefresh={() => void schema.refetch()}
      />
    </ReactFlowProvider>
  );
}

type NodeUiState = { measured?: { width: number; height: number }; dragging?: boolean };

function SchemaViewer({
  projectId,
  schema,
  canEditLinks,
  refreshing,
  onRefresh,
}: {
  projectId: string;
  schema: ProjectSchema;
  canEditLinks: boolean;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const { resolved } = useTheme();
  const rf = useReactFlow<SchemaFlowNode, RelationFlowEdge>();

  const [disabled, setDisabled] = useState<Set<string>>(() => new Set());
  const [manual, setManual] = useState<Record<string, XY>>(() => loadPositions(projectId));
  const [ui, setUi] = useState<Record<string, NodeUiState>>({});
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [focusField, setFocusField] = useState<{ nodeId: string; field: string | null } | null>(null);
  const [search, setSearch] = useState("");
  const [panelTab, setPanelTab] = useState<PanelTab>("conventions");
  const [panelOpen, setPanelOpen] = useState(true);
  const [addingLink, setAddingLink] = useState(false);
  const [exporting, setExporting] = useState<SchemaExportFormat | null>(null);

  const enabled = useMemo(
    () => new Set(schema.sources.map((s) => s.source_id).filter((id) => !disabled.has(id))),
    [schema.sources, disabled],
  );
  const graph = useMemo(() => buildGraph(schema, enabled), [schema, enabled]);
  const auto = useMemo(() => autoLayout(graph), [graph]);

  const positionOf = useCallback((id: string): XY => manual[id] ?? auto[id] ?? { x: 0, y: 0 }, [manual, auto]);
  const sizeOf = (id: string, fallbackHeight: number) => ({
    width: ui[id]?.measured?.width ?? NODE_WIDTH,
    height: ui[id]?.measured?.height ?? fallbackHeight,
  });

  const query = search.trim().toLowerCase();
  const matches = query ? graph.nodes.filter((n) => n.entity.name.toLowerCase().includes(query)) : [];
  const matchIds = new Set(matches.map((m) => m.id));

  const connectedToSelection = new Set<string>();
  if (selectedNode) {
    for (const e of graph.edges) {
      if (e.from.nodeId === selectedNode || e.to.nodeId === selectedNode) connectedToSelection.add(e.id);
    }
  }

  // ---- nodes ----
  const entityNodes: EntityFlowNode[] = graph.nodes.map((n) => ({
    id: n.id,
    type: "entity",
    position: positionOf(n.id),
    measured: ui[n.id]?.measured,
    dragging: ui[n.id]?.dragging,
    selected: selectedNode === n.id,
    data: {
      source: { source_id: n.source.source_id, name: n.source.name, kind: n.source.kind, engine: n.source.engine },
      entity: n.entity,
      issueCount: n.issues.length,
      issueFields: n.issues.map((i) => i.field).filter((f): f is string => Boolean(f)),
      highlight: matchIds.has(n.id),
      dimmed: query.length > 0 && !matchIds.has(n.id),
      focusField: focusField?.nodeId === n.id ? focusField.field : null,
    },
  }));

  const groupNodes: SourceGroupFlowNode[] = [];
  for (const source of schema.sources) {
    const members = graph.nodes.filter((n) => n.source.source_id === source.source_id);
    if (members.length === 0) continue;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const m of members) {
      const p = positionOf(m.id);
      const s = sizeOf(m.id, estimateHeight(m.entity));
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x + s.width);
      maxY = Math.max(maxY, p.y + s.height);
    }
    const id = `group::${source.source_id}`;
    groupNodes.push({
      id,
      type: "sourceGroup",
      position: { x: minX - GROUP_PAD, y: minY - GROUP_PAD - 24 },
      measured: ui[id]?.measured,
      draggable: false,
      selectable: false,
      focusable: false,
      zIndex: -1,
      data: {
        label: source.name,
        kind: source.kind,
        engine: source.engine,
        width: maxX - minX + GROUP_PAD * 2,
        height: maxY - minY + GROUP_PAD * 2 + 24,
      },
    });
  }
  const nodes: SchemaFlowNode[] = [...groupNodes, ...entityNodes];

  // ---- edges ----
  const nodeById = new Map(graph.nodes.map((n) => [n.id, n]));
  const edges: RelationFlowEdge[] = graph.edges.map((e) => {
    const { fromSide, toSide } = chooseSides(positionOf(e.from.nodeId), positionOf(e.to.nodeId), e.from.nodeId === e.to.nodeId);
    const fromHas = nodeById.get(e.from.nodeId)?.entity.fields.some((f) => f.name === e.from.field);
    const toHas = nodeById.get(e.to.nodeId)?.entity.fields.some((f) => f.name === e.to.field);
    const highlighted = connectedToSelection.has(e.id);
    return {
      id: e.id,
      type: "relation",
      source: e.from.nodeId,
      target: e.to.nodeId,
      sourceHandle: handleId(fromHas ? e.from.field : ENTITY_HANDLE, fromSide),
      targetHandle: handleId(toHas ? e.to.field : ENTITY_HANDLE, toSide),
      selected: selectedEdge === e.id,
      zIndex: highlighted || selectedEdge === e.id ? 1 : 0,
      data: {
        info: e,
        highlighted,
        dimmed: query.length > 0 && !matchIds.has(e.from.nodeId) && !matchIds.has(e.to.nodeId),
      },
    };
  });

  const onNodesChange = (changes: NodeChange<SchemaFlowNode>[]) => {
    let nextManual: Record<string, XY> | null = null;
    let dragEnded = false;
    let nextUi: Record<string, NodeUiState> | null = null;
    for (const c of changes) {
      if (c.type === "position") {
        if (c.id.startsWith("group::")) continue;
        if (c.position) {
          nextManual = nextManual ?? { ...manual };
          nextManual[c.id] = { x: Math.round(c.position.x), y: Math.round(c.position.y) };
        }
        nextUi = nextUi ?? { ...ui };
        nextUi[c.id] = { ...nextUi[c.id], dragging: c.dragging };
        if (c.dragging === false) dragEnded = true;
      } else if (c.type === "dimensions" && c.dimensions) {
        nextUi = nextUi ?? { ...ui };
        nextUi[c.id] = { ...nextUi[c.id], measured: { width: c.dimensions.width, height: c.dimensions.height } };
      } else if (c.type === "select") {
        if (c.selected) {
          setSelectedNode(c.id);
          setSelectedEdge(null);
        } else if (c.id === selectedNode) {
          setSelectedNode(null);
        }
      }
    }
    if (nextUi) setUi(nextUi);
    if (nextManual) setManual(nextManual);
    if (dragEnded) savePositions(projectId, nextManual ?? manual);
  };

  const focusNode = (nodeId: string, field: string | null = null) => {
    let pos: XY | undefined = manual[nodeId] ?? auto[nodeId];
    const [sourceId, entityName] = nodeId.split("::");
    if (!enabled.has(sourceId)) {
      const nextDisabled = new Set(disabled);
      nextDisabled.delete(sourceId);
      setDisabled(nextDisabled);
      const nextEnabled = new Set(enabled);
      nextEnabled.add(sourceId);
      pos = manual[nodeId] ?? autoLayout(buildGraph(schema, nextEnabled))[nodeId];
    }
    if (!pos) return;
    const entity = schema.sources.find((s) => s.source_id === sourceId)?.entities.find((e) => e.name === entityName);
    const size = sizeOf(nodeId, entity ? estimateHeight(entity) : 200);
    setSelectedNode(nodeId);
    setSelectedEdge(null);
    setFocusField({ nodeId, field });
    setPanelTab("details");
    void rf.setCenter(pos.x + size.width / 2, pos.y + Math.min(size.height / 2, 240), {
      zoom: Math.max(rf.getZoom(), 0.9),
      duration: 450,
    });
  };

  const onIssueFocus = (issue: ConventionIssue) => {
    if (!issue.entity) return;
    const sourceId =
      issue.source_id ??
      schema.sources.find((s) => s.entities.some((e) => e.name === issue.entity))?.source_id ??
      null;
    if (!sourceId) return;
    focusNode(nodeIdFor(sourceId, issue.entity), issue.field);
    setPanelTab("conventions");
  };

  const relayout = () => {
    setManual({});
    savePositions(projectId, {});
    requestAnimationFrame(() => void rf.fitView({ duration: 400, padding: 0.15 }));
    toast.info("Diagram re-laid out automatically.");
  };

  const doExport = async (format: SchemaExportFormat) => {
    setExporting(format);
    try {
      saveBlob(await api.schema.export(projectId, format));
    } catch (e) {
      toast.error(errorMessage(e), "Export failed");
    } finally {
      setExporting(null);
    }
  };

  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && matches[0]) {
      e.preventDefault();
      focusNode(matches[0].id);
    }
    if (e.key === "Escape") setSearch("");
  };

  const errorSources = schema.sources.filter((s) => s.status === "error");
  const hasSql = schema.sources.some((s) => s.kind === "sql" && s.status === "ok");
  const hasNosql = schema.sources.some((s) => s.kind === "nosql" && s.status === "ok");
  const warningCount = schema.conventions.filter((c) => c.severity === "warning").length;
  const selectedNodeInfo = selectedNode ? (nodeById.get(selectedNode) ?? null) : null;
  const selectedEdgeInfo = selectedEdge ? (graph.edges.find((e) => e.id === selectedEdge) ?? null) : null;

  return (
    <div className="flex flex-1 flex-col gap-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1 basis-48 sm:max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={onSearchKey}
            placeholder="Find table or collection…"
            aria-label="Search entities"
            className="h-9 w-full rounded-lg border border-border bg-surface pr-3 pl-8 text-base focus:border-accent focus:ring-3 focus:ring-ring focus:outline-none sm:text-sm"
          />
          {query && (
            <div className="absolute top-full right-0 left-0 z-20 mt-1 max-h-64 overflow-y-auto rounded-lg border border-border bg-surface p-1 shadow-lg">
              {matches.length === 0 ? (
                <p className="px-2 py-1.5 text-sm text-muted">No matches</p>
              ) : (
                matches.slice(0, 10).map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => focusNode(m.id)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-2"
                  >
                    <span className={cn("size-2 rounded-full", m.source.kind === "sql" ? "bg-sql" : "bg-nosql")} />
                    <span className="min-w-0 flex-1 truncate font-mono">{m.entity.name}</span>
                    <span className="truncate text-xs text-muted">{m.source.name}</span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        <Menu
          align="start"
          trigger={({ toggle, open }) => (
            <Button size="sm" onClick={toggle} aria-expanded={open} icon={<Filter className="size-3.5" />}>
              Sources {disabled.size > 0 && <Badge tone="accent">{enabled.size}</Badge>}
              <ChevronDown className="size-3.5" />
            </Button>
          )}
        >
          {() => (
            <div className="space-y-2 p-2">
              {schema.sources.map((s) => (
                <Checkbox
                  key={s.source_id}
                  checked={enabled.has(s.source_id)}
                  onChange={(e) => {
                    const next = new Set(disabled);
                    if (e.target.checked) next.delete(s.source_id);
                    else next.add(s.source_id);
                    setDisabled(next);
                  }}
                  label={s.name}
                  description={`${s.kind === "sql" ? "SQL" : "NoSQL"} · ${engineLabel(s.engine)} · ${s.entities.length} ${
                    s.kind === "sql" ? "tables" : "collections"
                  }${s.status === "error" ? " · error" : ""}`}
                />
              ))}
            </div>
          )}
        </Menu>

        <Button size="sm" icon={<LayoutGrid className="size-3.5" />} onClick={relayout} title="Discard manual positions and auto-arrange">
          Re-layout
        </Button>

        <Menu
          align="start"
          trigger={({ toggle, open }) => (
            <Button size="sm" onClick={toggle} aria-expanded={open} icon={<Download className="size-3.5" />} loading={exporting !== null}>
              Export <ChevronDown className="size-3.5" />
            </Button>
          )}
        >
          {(close) => (
            <>
              <MenuItem
                icon={<Download />}
                onClick={() => {
                  close();
                  if (hasSql) void doExport("sql");
                  else toast.info("This project has no reachable SQL database.");
                }}
              >
                Export SQL (.sql)
              </MenuItem>
              <MenuItem
                icon={<Download />}
                onClick={() => {
                  close();
                  if (hasNosql) void doExport("mongo");
                  else toast.info("This project has no reachable MongoDB database.");
                }}
              >
                Export MongoDB (.js)
              </MenuItem>
              <MenuItem
                icon={<Download />}
                onClick={() => {
                  close();
                  void doExport("bundle");
                }}
              >
                Export bundle (.zip)
              </MenuItem>
            </>
          )}
        </Menu>

        {canEditLinks && (
          <Button size="sm" icon={<Link2 className="size-3.5" />} onClick={() => setAddingLink(true)}>
            Add link
          </Button>
        )}

        <div className="ml-auto flex items-center gap-1">
          <span className="hidden text-xs text-muted md:inline">Generated {relativeTime(schema.generated_at)}</span>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Refresh schema"
            title="Refresh schema"
            onClick={onRefresh}
          >
            <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="hidden lg:inline-flex"
            aria-label={panelOpen ? "Hide side panel" : "Show side panel"}
            onClick={() => setPanelOpen((o) => !o)}
          >
            {panelOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          </Button>
        </div>
      </div>

      {errorSources.map((s) => (
        <Alert key={s.source_id} tone="danger" title={`Couldn't read ${s.name} (${engineLabel(s.engine)})`}>
          {s.error ?? "The database is unreachable."} Other databases are still shown. Check it on the Databases tab.
        </Alert>
      ))}

      <div className="flex flex-1 flex-col gap-3 lg:flex-row">
        <div className="relative h-[65dvh] min-h-[420px] overflow-hidden rounded-xl border border-border lg:h-auto lg:min-h-[600px] lg:flex-1">
          {graph.nodes.length === 0 ? (
            <div className="flex h-full items-center justify-center p-6">
              <EmptyState
                className="border-0"
                icon={<SquareMousePointer className="size-5" />}
                title={enabled.size === 0 ? "All sources hidden" : "No tables or collections yet"}
                description={
                  enabled.size === 0
                    ? "Turn a source back on from the Sources menu."
                    : "Create tables and collections on the Data tab."
                }
              />
            </div>
          ) : (
            <ReactFlow<SchemaFlowNode, RelationFlowEdge>
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onNodesChange={onNodesChange}
              onEdgeClick={(_, edge) => {
                setSelectedEdge(edge.id);
                setSelectedNode(null);
                setPanelTab("details");
                setPanelOpen(true);
              }}
              onNodeClick={(_, node) => {
                if (node.type !== "entity") return;
                setFocusField(null);
                setPanelTab("details");
              }}
              onPaneClick={() => {
                setSelectedEdge(null);
                setSelectedNode(null);
                setFocusField(null);
              }}
              connectionMode={ConnectionMode.Loose}
              nodesConnectable={false}
              elementsSelectable
              colorMode={resolved}
              fitView
              fitViewOptions={{ padding: 0.15 }}
              minZoom={0.1}
              maxZoom={2}
            >
              <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--border-strong)" />
              <Controls showInteractive={false} position="bottom-left" />
              <MiniMap
                pannable
                zoomable
                position="bottom-right"
                className="!hidden sm:!block"
                nodeColor={(n) =>
                  n.type === "sourceGroup"
                    ? "transparent"
                    : (n as EntityFlowNode).data.source.kind === "sql"
                      ? "var(--sql)"
                      : "var(--nosql)"
                }
                nodeStrokeWidth={0}
                maskColor="rgb(0 0 0 / 0.08)"
              />
            </ReactFlow>
          )}
        </div>

        {panelOpen && (
          <aside className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-surface lg:w-[340px] lg:shrink-0">
            <Tabs<PanelTab>
              className="px-2"
              value={panelTab}
              onChange={setPanelTab}
              items={[
                {
                  value: "conventions",
                  label: (
                    <>
                      Conventions
                      {schema.conventions.length > 0 && (
                        <Badge tone={warningCount > 0 ? "warning" : "info"}>{schema.conventions.length}</Badge>
                      )}
                    </>
                  ),
                  icon: <ListChecks className="size-3.5" />,
                },
                { value: "details", label: "Details", icon: <SquareMousePointer className="size-3.5" /> },
                { value: "legend", label: "Legend", icon: <BookOpen className="size-3.5" /> },
              ]}
            />
            <div className="max-h-[70dvh] min-h-0 flex-1 overflow-y-auto lg:max-h-[calc(100dvh-280px)]">
              {panelTab === "conventions" && (
                <ConventionsPanel issues={schema.conventions} sources={schema.sources} onFocus={onIssueFocus} />
              )}
              {panelTab === "details" && (
                <DetailsPanel
                  node={selectedNodeInfo}
                  edge={selectedEdgeInfo}
                  edges={graph.edges}
                  projectId={projectId}
                  canEditLinks={canEditLinks}
                  onFocusNode={(id, field) => focusNode(id, field ?? null)}
                  onLinkDeleted={() => setSelectedEdge(null)}
                />
              )}
              {panelTab === "legend" && <Legend />}
            </div>
          </aside>
        )}
      </div>

      {addingLink && (
        <AddLinkDialog
          projectId={projectId}
          schema={schema}
          initialFrom={
            selectedNodeInfo ? { sourceId: selectedNodeInfo.source.source_id, entity: selectedNodeInfo.entity.name } : null
          }
          onClose={() => setAddingLink(false)}
        />
      )}
    </div>
  );
}
