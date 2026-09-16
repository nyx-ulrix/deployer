import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { DataSource, Entity, JsonObject } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { cellText, formatNumber } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";
import { RowDialog } from "./RowDialog";

const PAGE_SIZES = [25, 50, 100];

export function SqlTableView({
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
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [orderBy, setOrderBy] = useState<string | undefined>(undefined);
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [editing, setEditing] = useState<JsonObject | "new" | null>(null);
  const [deleting, setDeleting] = useState<JsonObject | null>(null);
  const [dropping, setDropping] = useState(false);

  const params = { limit, offset, order_by: orderBy, order };
  const rows = useQuery({
    queryKey: qk.rows(project.id, source.id, entity.name, params),
    queryFn: () => api.rows.list(project.id, source.id, entity.name, params),
    placeholderData: keepPreviousData,
  });

  const invalidateRows = () =>
    queryClient.invalidateQueries({ queryKey: ["projects", project.id, "rows", source.id, entity.name] });

  const pkOf = (row: JsonObject, pk: string[]): JsonObject =>
    Object.fromEntries(pk.map((k) => [k, row[k] ?? null]));

  const remove = useMutation({
    mutationFn: (row: JsonObject) => api.rows.remove(project.id, source.id, entity.name, pkOf(row, rows.data?.primary_key ?? [])),
    onSuccess: () => {
      setDeleting(null);
      void invalidateRows();
      toast.success("Row deleted.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete row"),
  });

  const drop = useMutation({
    mutationFn: () => api.schema.dropTable(project.id, source.id, entity.name),
    onSuccess: () => {
      setDropping(false);
      void queryClient.invalidateQueries({ queryKey: qk.schema(project.id) });
      toast.success(`Table ${entity.name} dropped.`);
      onDropped();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't drop table"),
  });

  const sortBy = (col: string) => {
    if (orderBy === col) {
      if (order === "asc") setOrder("desc");
      else {
        setOrderBy(undefined);
        setOrder("asc");
      }
    } else {
      setOrderBy(col);
      setOrder("asc");
    }
    setOffset(0);
  };

  const data = rows.data;
  const pk = data?.primary_key ?? [];
  const editable = can("developer") && pk.length > 0;
  const total = data?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto min-w-0 truncate font-mono text-base font-semibold">{entity.name}</h2>
        <Button size="sm" variant="ghost" icon={<RefreshCw className={cn("size-3.5", rows.isFetching && "animate-spin")} />} onClick={() => void rows.refetch()}>
          Refresh
        </Button>
        {editable && (
          <Button size="sm" variant="primary" icon={<Plus className="size-3.5" />} onClick={() => setEditing("new")}>
            Add row
          </Button>
        )}
        {can("admin") && (
          <Button size="sm" variant="outline-danger" icon={<Trash2 className="size-3.5" />} onClick={() => setDropping(true)}>
            Drop table
          </Button>
        )}
      </div>

      {data && pk.length === 0 && (
        <Alert tone="warning" title="Read-only table">
          This table has no primary key, so rows can't be safely edited or deleted here. Add a primary key (convention
          S1) to enable editing.
        </Alert>
      )}
      {data && pk.length > 0 && !can("developer") && (
        <Alert tone="info">You have read-only access. Developers and above can edit rows.</Alert>
      )}

      {rows.isPending ? (
        <PageSpinner />
      ) : rows.isError ? (
        <ErrorState error={rows.error} onRetry={() => void rows.refetch()} />
      ) : data && data.rows.length === 0 && offset === 0 ? (
        <EmptyState
          title="No rows"
          description="This table is empty."
          action={
            editable ? (
              <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>
                Add row
              </Button>
            ) : undefined
          }
        />
      ) : data ? (
        <div className={cn("overflow-x-auto rounded-xl border border-border bg-surface", rows.isFetching && "opacity-80")}>
          <table className="w-full border-collapse text-left text-sm">
            <thead className="sticky top-0 bg-surface-2 text-xs">
              <tr>
                {data.columns.map((c) => (
                  <th key={c} className="border-b border-border px-3 py-2 font-semibold whitespace-nowrap">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-accent"
                      onClick={() => sortBy(c)}
                      aria-label={`Sort by ${c}`}
                    >
                      <span className="font-mono">{c}</span>
                      {pk.includes(c) && <Badge tone="warning">PK</Badge>}
                      {orderBy === c &&
                        (order === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
                    </button>
                  </th>
                ))}
                {editable && (
                  <th className="sticky right-0 border-b border-border bg-surface-2 px-2 py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.rows.map((row, i) => (
                <tr key={pk.length ? pk.map((k) => cellText(row[k])).join("|") : i} className="hover:bg-surface-2/60">
                  {data.columns.map((c) => {
                    const v = row[c];
                    const text = cellText(v);
                    return (
                      <td
                        key={c}
                        className={cn(
                          "max-w-72 truncate px-3 py-2 font-mono text-xs",
                          v === null || v === undefined ? "text-muted italic" : "",
                        )}
                        title={text.length > 40 ? text : undefined}
                      >
                        {text}
                      </td>
                    );
                  })}
                  {editable && (
                    <td className="sticky right-0 bg-surface px-1 py-1 whitespace-nowrap">
                      <Button size="icon-sm" variant="ghost" aria-label="Edit row" title="Edit" onClick={() => setEditing(row)}>
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        className="text-danger"
                        aria-label="Delete row"
                        title="Delete"
                        onClick={() => setDeleting(row)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {data && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
          <span>
            {formatNumber(from)}–{formatNumber(to)} of {formatNumber(total)}
          </span>
          <div className="flex items-center gap-2">
            <Select
              className="h-8 w-auto text-xs"
              aria-label="Rows per page"
              value={limit}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setOffset(0);
              }}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n} / page
                </option>
              ))}
            </Select>
            <Button size="icon-sm" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
              <ChevronLeft className="size-4" />
            </Button>
            <Button size="icon-sm" aria-label="Next page" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}

      {editing && data && (
        <RowDialog
          projectId={project.id}
          source={source}
          entity={entity}
          columns={data.columns}
          primaryKey={pk}
          row={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => void invalidateRows()}
        />
      )}
      {deleting && (
        <ConfirmDialog
          open
          onClose={() => setDeleting(null)}
          onConfirm={() => remove.mutate(deleting)}
          loading={remove.isPending}
          title="Delete this row?"
          description={
            <span>
              Row with{" "}
              <code className="font-mono">
                {pk.map((k) => `${k} = ${cellText(deleting[k])}`).join(", ")}
              </code>{" "}
              will be permanently deleted.
            </span>
          }
          confirmLabel="Delete row"
        />
      )}
      <ConfirmDialog
        open={dropping}
        onClose={() => setDropping(false)}
        onConfirm={() => drop.mutate()}
        loading={drop.isPending}
        title={`Drop table ${entity.name}?`}
        description="The table and all of its rows will be permanently deleted. Tables referencing it may block this."
        confirmText={entity.name}
        confirmLabel="Drop table"
      />
    </div>
  );
}
