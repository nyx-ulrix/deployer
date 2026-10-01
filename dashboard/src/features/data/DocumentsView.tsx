import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, CornerLeftUp, Filter, FolderTree, Pencil, Plus, RefreshCw, Trash2, X } from "lucide-react";
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
import { clampOffset } from "../../lib/pagination";
import { JobProgressPanel } from "../jobs/JobProgress";
import { useProjectContext } from "../projects/project-context";
import { docIdString, itemKeyId, parseJsonObject, pretty } from "./json";
import { JsonEditor } from "./JsonEditor";

const PAGE_SIZES = [10, 25, 50];

export function DocumentsView({
  source,
  entity,
  onDropped,
  onOpen,
}: {
  source: DataSource;
  entity: Entity;
  onDropped: () => void;
  /** Firestore: open another collection path (a subcollection, or the parent collection). */
  onOpen?: (path: string) => void;
}) {
  const { project, can } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [limit, setLimit] = useState(25);
  const [skip, setSkip] = useState(0);
  // DynamoDB pages with cursors (docs/CLOUD.md "C2-2"): the cursors of the pages before this one.
  const dynamo = source.engine === "dynamodb";
  // Firestore (docs/CLOUD.md "C2-3"): cursor pages too; collections are paths, users/u1/orders.
  const firestore = source.engine === "firestore";
  const cursorPaged = dynamo || firestore;
  const parentPath = firestore ? entity.name.split("/").slice(0, -2).join("/") : "";
  const [cursors, setCursors] = useState<string[]>([]);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const firstPage = () => {
    setSkip(0);
    setCursors([]);
    setCursor(undefined);
  };
  const noun = dynamo ? "item" : "document";
  const [filterText, setFilterText] = useState("");
  const [appliedFilter, setAppliedFilter] = useState<string | undefined>(undefined);
  const [editing, setEditing] = useState<JsonObject | "new" | null>(null);
  const [deleting, setDeleting] = useState<JsonObject | null>(null);
  const [dropping, setDropping] = useState(false);
  const [dropJob, setDropJob] = useState<string | null>(null);
  const dropped = () => {
    void queryClient.invalidateQueries({ queryKey: qk.schema(project.id) });
    toast.success(`Collection ${entity.name} dropped.`);
    onDropped();
  };

  const filterParse = parseJsonObject(filterText, { allowEmpty: true });
  const params = cursorPaged ? { filter: appliedFilter, limit, cursor } : { filter: appliedFilter, limit, skip };
  const docs = useQuery({
    queryKey: qk.documents(project.id, source.id, entity.name, params),
    queryFn: () => api.documents.list(project.id, source.id, entity.name, params),
    placeholderData: keepPreviousData,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["projects", project.id, "documents", source.id, entity.name] });

  const key = docs.data?.key ?? [];
  const idOf = (doc: JsonObject) => (dynamo ? itemKeyId(doc, key) : docIdString(doc._id));
  const remove = useMutation({
    mutationFn: (doc: JsonObject) => api.documents.remove(project.id, source.id, entity.name, idOf(doc) ?? ""),
    onSuccess: () => {
      setDeleting(null);
      void invalidate();
      toast.success(dynamo ? "Item deleted." : "Document deleted.");
    },
    onError: (e) => toast.error(errorMessage(e), `Couldn't delete ${noun}`),
  });

  const drop = useMutation({
    mutationFn: () => api.schema.dropCollection(project.id, source.id, entity.name),
    onSuccess: (res) => {
      setDropping(false);
      if (res.job) setDropJob(res.job.id);
      else dropped();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't drop collection"),
  });

  const applyFilter = () => {
    if (!filterParse.ok) return;
    setAppliedFilter(filterParse.value ? JSON.stringify(filterParse.value) : undefined);
    firstPage();
  };

  const total = docs.data?.total ?? 0;
  // Deleting the last document on a page leaves skip past the end: step back a page.
  if (!cursorPaged && docs.data && !docs.isPlaceholderData && clampOffset(skip, total, limit) !== skip) {
    setSkip(clampOffset(skip, total, limit));
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto min-w-0 truncate font-mono text-base font-semibold">{entity.name}</h2>
        {parentPath && onOpen && (
          <Button size="sm" variant="ghost" icon={<CornerLeftUp className="size-3.5" />} onClick={() => onOpen(parentPath)}>
            {parentPath}
          </Button>
        )}
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
            Insert {noun}
          </Button>
        )}
        {can("admin") && !cursorPaged && (
          <Button size="sm" variant="outline-danger" icon={<Trash2 className="size-3.5" />} onClick={() => setDropping(true)}>
            Drop collection
          </Button>
        )}
      </div>

      {dropJob && (
        <JobProgressPanel
          key={dropJob}
          projectId={project.id}
          jobId={dropJob}
          title={`Safety snapshot, then drop collection ${entity.name}`}
          onFinished={(job) => {
            if (job.status === "succeeded") dropped();
          }}
        />
      )}

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
            placeholder={
              dynamo
                ? `Equal values, e.g. { "${key[0] ?? "id"}": "..." } (naming the ${key[0] ?? "partition key"} is fastest)`
                : firestore
                  ? 'Equal values, e.g. { "status": "open" } or { "address.city": "Oslo" }'
                  : 'Filter, e.g. { "status": "active" }'
            }
            spellCheck={false}
            autoCapitalize="off"
            aria-label={dynamo ? "DynamoDB filter (JSON)" : firestore ? "Firestore filter (JSON)" : "MongoDB filter (JSON)"}
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
                firstPage();
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
          title={appliedFilter ? `No matching ${noun}s` : `No ${noun}s`}
          description={
            appliedFilter
              ? dynamo && docs.data.next_cursor
                ? "None on this stretch of the table; try the next page."
                : "Try a different filter."
              : `This ${dynamo ? "table" : "collection"} is empty.`
          }
        />
      ) : (
        <ul className={cn("space-y-2", docs.isFetching && "opacity-80")}>
          {docs.data.documents.map((doc, i) => {
            const id = idOf(doc);
            return (
              <li key={id ?? i} className="rounded-xl border border-border bg-surface">
                <div className="flex items-center gap-2 border-b border-border px-3 py-1.5">
                  <code className="min-w-0 flex-1 truncate font-mono text-xs text-muted">
                    {dynamo ? "key" : "_id"}: {id ?? "—"}
                  </code>
                  {firestore && id && onOpen && (
                    <Subcollections source={source} collection={entity.name} docId={id} onOpen={onOpen} />
                  )}
                  <CopyButton value={pretty(doc)} label="Copy JSON" className="size-7" />
                  {can("developer") && id && (
                    <>
                      <Button size="icon-sm" variant="ghost" aria-label={`Edit ${noun}`} title="Edit" onClick={() => setEditing(doc)}>
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        className="text-danger"
                        aria-label={`Delete ${noun}`}
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
          {dynamo ? (
            <span>
              Page {cursors.length + 1}
              {docs.data.total !== null && ` · about ${formatNumber(docs.data.total)} in the table (AWS updates this every few hours)`}
            </span>
          ) : firestore ? (
            <span>
              Page {cursors.length + 1} · {formatNumber(total)} {appliedFilter ? "matching" : "in the collection"}
            </span>
          ) : (
            <span>
              {formatNumber(total === 0 ? 0 : skip + 1)}–{formatNumber(Math.min(skip + limit, total))} of {formatNumber(total)}
            </span>
          )}
          <div className="flex items-center gap-2">
            <Select
              className="h-8 w-auto text-xs"
              aria-label={`${dynamo ? "Items" : "Documents"} per page`}
              value={limit}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                firstPage();
              }}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n} / page
                </option>
              ))}
            </Select>
            <Button
              size="icon-sm"
              aria-label="Previous page"
              disabled={cursorPaged ? cursors.length === 0 : skip === 0}
              onClick={() => {
                if (!cursorPaged) return setSkip(Math.max(0, skip - limit));
                setCursor(cursors.at(-1) || undefined);
                setCursors(cursors.slice(0, -1));
              }}
            >
              <ChevronLeft className="size-4" />
            </Button>
            <Button
              size="icon-sm"
              aria-label="Next page"
              disabled={cursorPaged ? !docs.data.next_cursor : skip + limit >= total}
              onClick={() => {
                if (!cursorPaged) return setSkip(skip + limit);
                setCursors([...cursors, cursor ?? ""]);
                setCursor(docs.data.next_cursor ?? undefined);
              }}
            >
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
          itemKey={dynamo ? key : null}
          firestore={firestore}
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
          title={`Delete this ${noun}?`}
          description={`${dynamo ? "Item" : "Document"} ${idOf(deleting)} will be permanently deleted.`}
          confirmLabel={`Delete ${noun}`}
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

/** Firestore: a document's own collections, listed on demand (each one is a read). */
function Subcollections({
  source,
  collection,
  docId,
  onOpen,
}: {
  source: DataSource;
  collection: string;
  docId: string;
  onOpen: (path: string) => void;
}) {
  const { project } = useProjectContext();
  const [open, setOpen] = useState(false);
  const subs = useQuery({
    queryKey: ["projects", project.id, "subcollections", source.id, collection, docId],
    queryFn: () => api.documents.subcollections(project.id, source.id, collection, docId),
    enabled: open,
  });
  return (
    <span className="relative">
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label="Collections inside this document"
        title="Collections inside this document"
        onClick={() => setOpen(!open)}
      >
        <FolderTree className="size-3.5" />
      </Button>
      {open && (
        <span className="absolute right-0 z-10 mt-1 block w-64 rounded-lg border border-border bg-surface p-2 text-xs shadow-lg">
          {subs.isPending ? (
            "Looking…"
          ) : subs.isError ? (
            errorMessage(subs.error)
          ) : subs.data.collections.length === 0 ? (
            "No collections inside this document."
          ) : (
            subs.data.collections.map((path) => (
              <button
                key={path}
                type="button"
                className="block w-full truncate rounded px-1.5 py-1 text-left font-mono hover:bg-surface-2"
                onClick={() => onOpen(path)}
              >
                {path.split("/").at(-1)}
              </button>
            ))
          )}
        </span>
      )}
    </span>
  );
}

function DocumentDialog({
  projectId,
  sourceId,
  collection,
  itemKey,
  firestore,
  doc,
  onClose,
  onSaved,
}: {
  projectId: string;
  sourceId: string;
  collection: string;
  /** DynamoDB: the key attributes, which identify the item and cannot be edited. */
  itemKey: string[] | null;
  /** Firestore: plain JSON with `$` forms for its own types. */
  firestore: boolean;
  doc: JsonObject | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isNew = doc === null;
  const fixed = itemKey ?? ["_id"]; // never sent in `set`
  const docId = doc ? (itemKey ? itemKeyId(doc, itemKey) : docIdString(doc._id)) : null;
  const [text, setText] = useState(() => {
    if (!doc) return itemKey ? pretty(Object.fromEntries(itemKey.map((k) => [k, ""]))) : "{\n  \n}";
    const rest: JsonObject = { ...doc };
    for (const k of fixed) delete rest[k];
    return pretty(rest);
  });
  const parsed = parseJsonObject(text);

  const save = useMutation({
    mutationFn: () => {
      if (!parsed.ok || !parsed.value) throw new Error("Invalid JSON");
      const value = parsed.value;
      if (isNew) return api.documents.insert(projectId, sourceId, collection, value);
      const set: JsonObject = { ...value };
      for (const k of fixed) delete set[k];
      const unset = Object.keys(doc).filter((k) => !fixed.includes(k) && !(k in set));
      return api.documents.update(projectId, sourceId, collection, docId ?? "", set, unset.length ? unset : undefined);
    },
    onSuccess: () => {
      const noun = itemKey ? "Item" : "Document";
      toast.success(isNew ? `${noun} inserted.` : `${noun} updated.`);
      onSaved();
      onClose();
    },
  });

  return (
    <Dialog
      open
      onClose={onClose}
      title={isNew ? `Insert into ${collection}` : itemKey ? "Edit item" : "Edit document"}
      description={
        itemKey
          ? isNew
            ? `Fill in the key (${itemKey.join(", ")}) and any other fields. Plain JSON; a set is { "$set": ["a", "b"] }, binary is { "$base64": "..." }.`
            : `Key ${docId} (it cannot change) — top-level fields you remove are deleted.`
          : isNew && firestore
            ? 'Plain JSON. "_id" picks the document id (leave it out and Firestore makes one). Firestore types: { "$timestamp": "2026-01-01T00:00:00Z" }, { "$ref": "users/u1" }, { "$base64": "..." }, { "$geo": { "latitude": 1, "longitude": 2 } }.'
            : isNew
            ? "Relaxed Extended JSON is supported, e.g. { \"createdAt\": { \"$date\": \"2026-01-01T00:00:00Z\" } }. Omit _id to generate one."
            : `_id ${docId} — top-level fields you remove are unset.`
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
