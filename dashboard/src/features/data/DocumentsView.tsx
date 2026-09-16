import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Filter, Pencil, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { DataSource, Entity, JsonObject } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyButton } from "../../components/ui/CopyField";
import { Dialog } from "../../components/ui/Dialog";
import { Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { formatNumber } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";
import { docIdString, parseJsonObject, pretty } from "./json";
import { JsonEditor } from "./JsonEditor";

const PAGE_SIZES = [10, 25, 50];

export function DocumentsView({
  source,
  entity,
  onDropped,
}: {
  source: DataSource;
  entity: Entity;
  onDropped: () => void;
}) {
  const { project, can } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [limit, setLimit] = useState(25);
  const [skip, setSkip] = useState(0);
  const [filterText, setFilterText] = useState("");
  const [appliedFilter, setAppliedFilter] = useState<string | undefined>(undefined);
  const [editing, setEditing] = useState<JsonObject | "new" | null>(null);
  const [deleting, setDeleting] = useState<JsonObject | null>(null);
  const [dropping, setDropping] = useState(false);

  const filterParse = parseJsonObject(filterText, { allowEmpty: true });
  const params = { filter: appliedFilter, limit, skip };
  const docs = useQuery({
    queryKey: qk.documents(project.id, source.id, entity.name, params),
    queryFn: () => api.documents.list(project.id, source.id, entity.name, params),
    placeholderData: keepPreviousData,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["projects", project.id, "documents", source.id, entity.name] });

  const remove = useMutation({
    mutationFn: (doc: JsonObject) => api.documents.remove(project.id, source.id, entity.name, docIdString(doc._id) ?? ""),
    onSuccess: () => {
      setDeleting(null);
      void invalidate();
      toast.success("Document deleted.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete document"),
  });

  const drop = useMutation({
    mutationFn: () => api.schema.dropCollection(project.id, source.id, entity.name),
    onSuccess: () => {
      setDropping(false);
      void queryClient.invalidateQueries({ queryKey: qk.schema(project.id) });
      toast.success(`Collection ${entity.name} dropped.`);
      onDropped();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't drop collection"),
  });

  const applyFilter = () => {
    if (!filterParse.ok) return;
    setAppliedFilter(filterParse.value ? JSON.stringify(filterParse.value) : undefined);
    setSkip(0);
  };

  const total = docs.data?.total ?? 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto min-w-0 truncate font-mono text-base font-semibold">{entity.name}</h2>
        <Button
          size="sm"
          variant="ghost"
          icon={<RefreshCw className={cn("size-3.5", docs.isFetching && "animate-spin")} />}
          onClick={() => void docs.refetch()}
        >
          Refresh
        </Button>
        {can("developer") && (
          <Button size="sm" variant="primary" icon={<Plus className="size-3.5" />} onClick={() => setEditing("new")}>
            Insert document
          </Button>
        )}
        {can("admin") && (
          <Button size="sm" variant="outline-danger" icon={<Trash2 className="size-3.5" />} onClick={() => setDropping(true)}>
            Drop collection
          </Button>
        )}
      </div>

      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          applyFilter();
        }}
      >
        <div className="relative min-w-0 flex-1">
          <Filter className="pointer-events-none absolute top-3 left-3 size-3.5 text-muted" />
          <input
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder='Filter, e.g. { "status": "active" }'
            spellCheck={false}
            autoCapitalize="off"
            aria-label="MongoDB filter (JSON)"
            aria-invalid={!filterParse.ok}
            className={cn(
              "h-10 w-full rounded-lg border bg-surface pr-3 pl-8 font-mono text-base focus:ring-3 focus:ring-ring focus:outline-none sm:text-xs",
              filterParse.ok ? "border-border focus:border-accent" : "border-danger",
            )}
          />
        </div>
        <div className="flex gap-2">
          <Button type="submit" disabled={!filterParse.ok}>
            Apply
          </Button>
          {appliedFilter && (
            <Button
              variant="ghost"
              icon={<X className="size-4" />}
              onClick={() => {
                setFilterText("");
                setAppliedFilter(undefined);
                setSkip(0);
              }}
            >
              Clear
            </Button>
          )}
        </div>
      </form>
      {!filterParse.ok && <p className="text-xs text-danger">{filterParse.error}</p>}

      {docs.isPending ? (
        <PageSpinner />
      ) : docs.isError ? (
        <ErrorState error={docs.error} onRetry={() => void docs.refetch()} />
      ) : docs.data.documents.length === 0 ? (
        <EmptyState
          title={appliedFilter ? "No matching documents" : "No documents"}
          description={appliedFilter ? "Try a different filter." : "This collection is empty."}
        />
      ) : (
        <ul className={cn("space-y-2", docs.isFetching && "opacity-80")}>
          {docs.data.documents.map((doc, i) => {
            const id = docIdString(doc._id);
            return (
              <li key={id ?? i} className="rounded-xl border border-border bg-surface">
                <div className="flex items-center gap-2 border-b border-border px-3 py-1.5">
                  <code className="min-w-0 flex-1 truncate font-mono text-xs text-muted">_id: {id ?? "—"}</code>
                  <CopyButton value={pretty(doc)} label="Copy JSON" className="size-7" />
                  {can("developer") && id && (
                    <>
                      <Button size="icon-sm" variant="ghost" aria-label="Edit document" title="Edit" onClick={() => setEditing(doc)}>
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        className="text-danger"
                        aria-label="Delete document"
                        title="Delete"
                        onClick={() => setDeleting(doc)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </>
                  )}
                </div>
                <pre className="max-h-72 overflow-auto px-3 py-2 font-mono text-xs leading-5">{pretty(doc)}</pre>
              </li>
            );
          })}
        </ul>
      )}

      {docs.data && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
          <span>
            {formatNumber(total === 0 ? 0 : skip + 1)}–{formatNumber(Math.min(skip + limit, total))} of {formatNumber(total)}
          </span>
          <div className="flex items-center gap-2">
            <Select
              className="h-8 w-auto text-xs"
              aria-label="Documents per page"
              value={limit}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setSkip(0);
              }}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n} / page
                </option>
              ))}
            </Select>
            <Button size="icon-sm" aria-label="Previous page" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - limit))}>
              <ChevronLeft className="size-4" />
            </Button>
            <Button size="icon-sm" aria-label="Next page" disabled={skip + limit >= total} onClick={() => setSkip(skip + limit)}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}

      {editing && (
        <DocumentDialog
          projectId={project.id}
          sourceId={source.id}
          collection={entity.name}
          doc={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => void invalidate()}
        />
      )}
      {deleting && (
        <ConfirmDialog
          open
          onClose={() => setDeleting(null)}
          onConfirm={() => remove.mutate(deleting)}
          loading={remove.isPending}
          title="Delete this document?"
          description={`Document ${docIdString(deleting._id)} will be permanently deleted.`}
          confirmLabel="Delete document"
        />
      )}
      <ConfirmDialog
        open={dropping}
        onClose={() => setDropping(false)}
        onConfirm={() => drop.mutate()}
        loading={drop.isPending}
        title={`Drop collection ${entity.name}?`}
        description="The collection, its indexes and all documents will be permanently deleted."
        confirmText={entity.name}
        confirmLabel="Drop collection"
      />
    </div>
  );
}

function DocumentDialog({
  projectId,
  sourceId,
  collection,
  doc,
  onClose,
  onSaved,
}: {
  projectId: string;
  sourceId: string;
  collection: string;
  doc: JsonObject | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isNew = doc === null;
  const [text, setText] = useState(() => {
    if (!doc) return "{\n  \n}";
    const rest: JsonObject = { ...doc };
    delete rest._id;
    return pretty(rest);
  });
  const parsed = parseJsonObject(text);

  const save = useMutation({
    mutationFn: () => {
      if (!parsed.ok || !parsed.value) throw new Error("Invalid JSON");
      const value = parsed.value;
      if (isNew) return api.documents.insert(projectId, sourceId, collection, value);
      const set: JsonObject = { ...value };
      delete set._id;
      const unset = Object.keys(doc).filter((k) => k !== "_id" && !(k in set));
      return api.documents.update(projectId, sourceId, collection, docIdString(doc._id) ?? "", set, unset.length ? unset : undefined);
    },
    onSuccess: () => {
      toast.success(isNew ? "Document inserted." : "Document updated.");
      onSaved();
      onClose();
    },
  });

  return (
    <Dialog
      open
      onClose={onClose}
      title={isNew ? `Insert into ${collection}` : "Edit document"}
      description={
        isNew
          ? "Relaxed Extended JSON is supported, e.g. { \"createdAt\": { \"$date\": \"2026-01-01T00:00:00Z\" } }. Omit _id to generate one."
          : `_id ${docIdString(doc._id)} — top-level fields you remove are unset.`
      }
      size="lg"
      dismissible={!save.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} disabled={!parsed.ok} onClick={() => save.mutate()}>
            {isNew ? "Insert" : "Save"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <JsonEditor label="Document" value={text} onChange={setText} rows={16} />
        {save.error && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
      </div>
    </Dialog>
  );
}
