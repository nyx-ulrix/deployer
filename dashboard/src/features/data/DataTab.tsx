import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Database, FileJson, Leaf, Plus, Table2 } from "lucide-react";
import { useDataSources, useSchema } from "../../api/hooks";
import type { DataSource, Entity } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { engineLabel, formatNumber } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";
import { CreateCollectionDialog } from "./CreateCollectionDialog";
import { CreateTableDialog } from "./CreateTableDialog";
import { DocumentsView } from "./DocumentsView";
import { SqlTableView } from "./SqlTableView";

export function DataTab() {
  const { project, can } = useProjectContext();
  const sources = useDataSources(project.id);
  const schema = useSchema(project.id);
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);

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
  const entity = entities.find((e) => e.name === entityName) ?? null;
  const isSql = source.kind === "sql";

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
              {s.name} ({s.kind === "sql" ? "SQL" : "NoSQL"} · {engineLabel(s.engine)})
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
              aria-label={isSql ? "Table" : "Collection"}
              value={entity?.name ?? ""}
              onChange={(e) => select({ entity: e.target.value || null })}
            >
              <option value="">{isSql ? "Choose a table…" : "Choose a collection…"}</option>
              {entities.map((e) => (
                <option key={e.name} value={e.name}>
                  {e.name}
                </option>
              ))}
            </Select>
            <nav className="hidden max-h-[60vh] overflow-y-auto rounded-xl border border-border bg-surface p-1 lg:block">
              <p className="px-2 pt-1.5 pb-1 text-xs font-medium tracking-wide text-muted uppercase">
                {isSql ? "Tables" : "Collections"}
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
            {can("developer") && (
              <Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
                {isSql ? "Create table" : "Create collection"}
              </Button>
            )}
          </>
        )}
      </aside>

      <section className="min-w-0 flex-1">
        {entity ? (
          isSql ? (
            <SqlTableView key={`${source.id}/${entity.name}`} source={source} entity={entity} onDropped={() => select({ entity: null })} />
          ) : (
            <DocumentsView key={`${source.id}/${entity.name}`} source={source} entity={entity} onDropped={() => select({ entity: null })} />
          )
        ) : (
          <EmptyState
            icon={isSql ? <Database className="size-5" /> : <Leaf className="size-5" />}
            title={isSql ? "Pick a table" : "Pick a collection"}
            description={
              entities.length === 0 && !schema.isPending
                ? `This database has no ${isSql ? "tables" : "collections"} yet.`
                : `Choose a ${isSql ? "table" : "collection"} to browse its ${isSql ? "rows" : "documents"}.`
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
