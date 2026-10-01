import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Database, Download, FileJson, FolderOpen, History, Leaf, Plus, Table2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api } from "../../api/endpoints";
import { useDataSources, useSchema } from "../../api/hooks";
import type { DataSource, Entity } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Input, Select } from "../../components/ui/Input";
import { useToast } from "../../components/ui/toast-context";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { engineLabel, formatNumber } from "../../lib/format";
import { useDeviceNames } from "../devices/useDeviceNames";
import { useProjectContext } from "../projects/project-context";
import { CreateCollectionDialog } from "./CreateCollectionDialog";
import { CreateTableDialog } from "./CreateTableDialog";
import { downloadText } from "../query/csv";
import { DocumentsView } from "./DocumentsView";
import { SqlTableView } from "./SqlTableView";

export function DataTab() {
  const { project, can } = useProjectContext();
  const sources = useDataSources(project.id);
  const schema = useSchema(project.id);
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const deviceName = useDeviceNames(project.id, sources.data?.some((s) => s.device_id) ?? false);

  if (sources.isPending) return <PageSpinner />;
  if (sources.isError) return <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />;
  if (sources.data.length === 0) {
    return (
      <EmptyState
        icon={<Database className="size-5" />}
        title="No databases yet"
        description="Add a database on the Databases tab to browse its data here."
      />
    );
  }

  const sourceId = params.get("source");
  const source: DataSource = sources.data.find((s) => s.id === sourceId) ?? sources.data[0];
  const sourceSchema = schema.data?.sources.find((s) => s.source_id === source.id);
  const entities: Entity[] = sourceSchema?.entities ?? [];
  const entityName = params.get("entity");
  const isSql = source.kind === "sql";
  const dynamo = source.engine === "dynamodb"; // tables of items; tables are added in AWS, not here
  // Firestore (docs/CLOUD.md "C2-3"): any collection path opens, a subcollection or one with no documents yet.
  const firestore = source.engine === "firestore";
  const entity =
    entities.find((e) => e.name === entityName) ??
    (firestore && entityName ? { name: entityName, type: "collection" as const, row_count: null, fields: [], indexes: [], validator: null } : null);
  const entityNoun = isSql || dynamo ? "table" : "collection";

  const select = (next: { source?: string; entity?: string | null }) => {
    const p = new URLSearchParams();
    p.set("source", next.source ?? source.id);
    const ent = next.entity === undefined ? entityName : next.entity;
    if (ent) p.set("entity", ent);
    setParams(p, { replace: true });
  };

  return (
    <div className="flex flex-1 flex-col gap-4 lg:flex-row">
      <aside className="flex shrink-0 flex-col gap-3 lg:w-64">
        <Select
          aria-label="Data source"
          value={source.id}
          onChange={(e) => select({ source: e.target.value, entity: null })}
        >
          {sources.data.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({s.kind === "sql" ? "SQL" : "NoSQL"} · {engineLabel(s.engine)}
              {deviceName(s) ? ` · on ${deviceName(s)}` : ""})
            </option>
          ))}
        </Select>

        {schema.isPending ? (
          <PageSpinner />
        ) : schema.isError ? (
          <ErrorState error={schema.error} onRetry={() => void schema.refetch()} />
        ) : sourceSchema?.status === "error" ? (
          <Alert tone="danger" title="Database unreachable">
            {sourceSchema.error ?? "Couldn't read this database."}
          </Alert>
        ) : (
          <>
            {/* Phone: a select; desktop: a list */}
            <Select
              className="lg:hidden"
              aria-label={isSql || dynamo ? "Table" : "Collection"}
              value={entity?.name ?? ""}
              onChange={(e) => select({ entity: e.target.value || null })}
            >
              <option value="">{`Choose a ${entityNoun}…`}</option>
              {entities.map((e) => (
                <option key={e.name} value={e.name}>
                  {e.name}
                </option>
              ))}
            </Select>
            <nav className="hidden max-h-[60vh] overflow-y-auto rounded-xl border border-border bg-surface p-1 lg:block">
              <p className="px-2 pt-1.5 pb-1 text-xs font-medium tracking-wide text-muted uppercase">
                {isSql || dynamo ? "Tables" : "Collections"}
              </p>
              {entities.length === 0 && <p className="px-2 py-2 text-sm text-muted">None yet.</p>}
              {entities.map((e) => (
                <button
                  key={e.name}
                  type="button"
                  onClick={() => select({ entity: e.name })}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm",
                    entity?.name === e.name ? "bg-accent-soft text-accent" : "hover:bg-surface-2",
                  )}
                >
                  {isSql ? <Table2 className="size-3.5 shrink-0" /> : <FileJson className="size-3.5 shrink-0" />}
                  <span className="min-w-0 flex-1 truncate">{e.name}</span>
                  {e.row_count !== null && <span className="text-xs text-muted tabular-nums">{formatNumber(e.row_count)}</span>}
                </button>
              ))}
            </nav>
            {firestore && <OpenCollection onOpen={(path) => select({ entity: path })} />}
            {firestore && <ExportButton projectId={project.id} source={source} />}
            {can("developer") && !dynamo && !firestore && (
              <Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
                {isSql ? "Create table" : "Create collection"}
              </Button>
            )}
            {(source.mode === "managed" || dynamo) && (
              <Link
                to={`/projects/${project.id}/backups?source=${encodeURIComponent(source.id)}`}
                className="inline-flex items-center gap-1.5 self-start px-1 text-sm text-accent hover:underline"
              >
                <History className="size-3.5" /> Versions &amp; backups
              </Link>
            )}
          </>
        )}
      </aside>

      <section className="min-w-0 flex-1">
        {entity ? (
          isSql ? (
            <SqlTableView key={`${source.id}/${entity.name}`} source={source} entity={entity} onDropped={() => select({ entity: null })} />
          ) : (
            <DocumentsView
              key={`${source.id}/${entity.name}`}
              source={source}
              entity={entity}
              onDropped={() => select({ entity: null })}
              onOpen={(path) => select({ entity: path })}
            />
          )
        ) : (
          <EmptyState
            icon={isSql ? <Database className="size-5" /> : <Leaf className="size-5" />}
            title={`Pick a ${entityNoun}`}
            description={
              entities.length === 0 && !schema.isPending
                ? `This database has no ${entityNoun}s yet.`
                : `Choose a ${entityNoun} to browse its ${isSql ? "rows" : dynamo ? "items" : "documents"}.`
            }
          />
        )}
      </section>

      {creating &&
        (isSql ? (
          <CreateTableDialog
            projectId={project.id}
            source={source}
            entities={entities}
            onClose={() => setCreating(false)}
            onCreated={(name) => select({ entity: name })}
          />
        ) : (
          <CreateCollectionDialog
            projectId={project.id}
            source={source}
            onClose={() => setCreating(false)}
            onCreated={(name) => select({ entity: name })}
          />
        ))}
    </div>
  );
}

/** Firestore: open a collection by its path (a new one appears with its first document). */
function OpenCollection({ onOpen }: { onOpen: (path: string) => void }) {
  const [path, setPath] = useState("");
  const clean = path.trim().replace(/^\/+|\/+$/g, "");
  const valid = clean !== "" && clean.split("/").length % 2 === 1 && !clean.split("/").includes("");
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onOpen(clean);
      }}
    >
      <Input
        aria-label="Collection path"
        placeholder="Open a collection path, e.g. users/u1/orders"
        value={path}
        onChange={(e) => setPath(e.target.value)}
        spellCheck={false}
        autoCapitalize="off"
        className="min-w-0 flex-1 font-mono text-xs"
      />
      <Button type="submit" size="icon" aria-label="Open collection" title="Open (or start) this collection" disabled={!valid}>
        <FolderOpen className="size-4" />
      </Button>
    </form>
  );
}

/** Firestore: every document of the top-level collections as one JSON file (docs/CLOUD.md "C2-3"). */
function ExportButton({ projectId, source }: { projectId: string; source: DataSource }) {
  const toast = useToast();
  const exp = useMutation({
    mutationFn: () => api.cloud.firestoreExport(projectId, source.id),
    onSuccess: (out) => {
      downloadText(`${source.name}-firestore.json`, JSON.stringify(out, null, 2), "application/json");
      toast.success(
        out.truncated
          ? `Exported the first ${out.documents} documents (the limit for one export).`
          : `Exported ${out.documents} documents.`,
      );
    },
    onError: (e) => toast.error(errorMessage(e), "Export failed"),
  });
  return (
    <Button size="sm" variant="ghost" icon={<Download className="size-3.5" />} loading={exp.isPending} onClick={() => exp.mutate()}>
      Export as JSON
    </Button>
  );
}
