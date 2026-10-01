import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, CornerLeftUp, FolderOpen, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api } from "../../api/endpoints";
import type { DataSource, JsonValue } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input, Textarea } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { useProjectContext } from "../projects/project-context";
import { pretty } from "./json";
import { childPath, cleanRtdbPath, isBranch, isRtdbKey, parentPath, preview } from "./rtdb";

const SHOWN = 200; // children listed per branch; deeper paths open on their own

type Edit = { mode: "edit" | "add"; path: string };

/** docs/CLOUD.md "C2-4": a Firebase Realtime Database as a tree that opens one branch at a time (shallow reads). */
export function RtdbView({ source }: { source: DataSource }) {
  const { project, can } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [root, setRoot] = useState("");
  const [pathText, setPathText] = useState("");
  const [editing, setEditing] = useState<Edit | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const cleanPath = cleanRtdbPath(pathText);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["projects", project.id, "rtdb", source.id] });
  const remove = useMutation({
    mutationFn: (path: string) => api.rtdb.remove(project.id, source.id, path),
    onSuccess: (_, path) => {
      toast.success(`Deleted /${path}.`);
      setDeleting(null);
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e), "Delete failed"),
  });
  const open = (path: string) => {
    setRoot(path);
    setPathText(path);
  };
  const actions = can("developer")
    ? { onEdit: (path: string) => setEditing({ mode: "edit", path }), onAdd: (path: string) => setEditing({ mode: "add", path }), onDelete: setDeleting }
    : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto min-w-0 truncate font-mono text-base font-semibold">/{root}</h2>
        {root && (
          <Button size="sm" variant="ghost" icon={<CornerLeftUp className="size-3.5" />} onClick={() => open(parentPath(root))}>
            Up
          </Button>
        )}
        <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} onClick={() => void invalidate()}>
          Refresh
        </Button>
        {actions && (
          <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => actions.onAdd(root)}>
            Add here
          </Button>
        )}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (cleanPath !== null) open(cleanPath);
        }}
      >
        <Input
          aria-label="Path"
          placeholder="Open a path, e.g. users/ann (empty: the whole database)"
          value={pathText}
          onChange={(e) => setPathText(e.target.value)}
          aria-invalid={cleanPath === null}
          spellCheck={false}
          autoCapitalize="off"
          className="min-w-0 flex-1 font-mono text-xs"
        />
        <Button type="submit" size="icon" aria-label="Open path" disabled={cleanPath === null}>
          <FolderOpen className="size-4" />
        </Button>
      </form>
      <p className="text-xs text-muted">
        One JSON tree: click ▸ to open a branch (each opens with one small read, so big databases stay fast). Keys can&apos;t
        contain . $ # [ ] /. Search and sort children in the Query tab, e.g.{" "}
        <code className="font-mono">{'{ "path": "users", "orderBy": "age", "limitToFirst": 20 }'}</code>.
      </p>
      <div className="overflow-x-auto rounded-xl border border-border bg-surface p-2 font-mono text-xs">
        <Branch key={root} source={source} path={root} actions={actions} onOpen={open} />
      </div>
      {editing && (
        <ValueDialog
          source={source}
          edit={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void invalidate();
          }}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (deleting !== null) remove.mutate(deleting);
        }}
        loading={remove.isPending}
        title={`Delete /${deleting ?? ""}?`}
        description="This removes the value at this path and everything under it from your Realtime Database. Apps listening to it see it disappear at once. This can't be undone."
        confirmLabel="Delete"
      />
    </div>
  );
}

type Actions = { onEdit: (path: string) => void; onAdd: (path: string) => void; onDelete: (path: string) => void } | null;

function Branch({
  source,
  path,
  actions,
  onOpen,
}: {
  source: DataSource;
  path: string;
  actions: Actions;
  onOpen: (path: string) => void;
}) {
  const { project } = useProjectContext();
  const node = useQuery({
    queryKey: ["projects", project.id, "rtdb", source.id, path, "shallow"],
    queryFn: () => api.rtdb.read(project.id, source.id, path, { shallow: true }),
  });
  if (node.isPending) return <p className="px-2 py-1 text-muted">Loading…</p>;
  if (node.isError) return <p className="px-2 py-1 text-danger">{errorMessage(node.error)}</p>;
  if (!node.data.children) {
    // A plain value (an empty path reads as null).
    return node.data.value === null ? (
      <p className="px-2 py-1 text-muted">Nothing here yet{actions ? " — use Add here." : "."}</p>
    ) : (
      <Row name={path.split("/").at(-1) || "/"} path={path} value={node.data.value} actions={actions} />
    );
  }
  const children = node.data.children;
  return (
    <ul>
      {children.length === 0 && <li className="px-2 py-1 text-muted">Empty.</li>}
      {children.slice(0, SHOWN).map((c) =>
        isBranch(c.value) ? (
          <Expandable key={c.key} source={source} path={childPath(path, c.key)} name={c.key} actions={actions} onOpen={onOpen} />
        ) : (
          <li key={c.key}>
            <Row name={c.key} path={childPath(path, c.key)} value={c.value} actions={actions} />
          </li>
        ),
      )}
      {children.length > SHOWN && (
        <li className="px-2 py-1 font-sans text-muted">
          …and {children.length - SHOWN} more. Open a deeper path above, or search them in the Query tab.
        </li>
      )}
    </ul>
  );
}

function Expandable({
  source,
  path,
  name,
  actions,
  onOpen,
}: {
  source: DataSource;
  path: string;
  name: string;
  actions: Actions;
  onOpen: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <li>
      <div className="group flex items-center gap-1 rounded px-1 hover:bg-surface-2">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-1 py-1 text-left"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
          <span className="truncate font-medium">{name}</span>
        </button>
        <RowActions path={path} actions={actions} branch onOpen={onOpen} />
      </div>
      {expanded && (
        <div className="ml-3 border-l border-border pl-2">
          <Branch source={source} path={path} actions={actions} onOpen={onOpen} />
        </div>
      )}
    </li>
  );
}

function Row({ name, path, value, actions }: { name: string; path: string; value: JsonValue; actions: Actions }) {
  return (
    <div className="group flex items-center gap-2 rounded px-1 py-1 pl-5 hover:bg-surface-2">
      <span className="shrink-0 font-medium">{name}:</span>
      <span className="min-w-0 flex-1 truncate text-muted" title={JSON.stringify(value)}>
        {preview(value)}
      </span>
      <RowActions path={path} actions={actions} />
    </div>
  );
}

function RowActions({
  path,
  actions,
  branch = false,
  onOpen,
}: {
  path: string;
  actions: Actions;
  branch?: boolean;
  onOpen?: (path: string) => void;
}) {
  return (
    <span className="flex shrink-0 gap-0.5 opacity-100 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
      {branch && onOpen && (
        <Button size="icon-sm" variant="ghost" aria-label={`Open /${path}`} title="Open this path" onClick={() => onOpen(path)}>
          <FolderOpen className="size-3.5" />
        </Button>
      )}
      {actions && path && (
        <>
          {branch && (
            <Button size="icon-sm" variant="ghost" aria-label={`Add under /${path}`} title="Add a child" onClick={() => actions.onAdd(path)}>
              <Plus className="size-3.5" />
            </Button>
          )}
          <Button size="icon-sm" variant="ghost" aria-label={`Edit /${path}`} title="Edit as JSON" onClick={() => actions.onEdit(path)}>
            <Pencil className="size-3.5" />
          </Button>
          <Button size="icon-sm" variant="ghost" aria-label={`Delete /${path}`} title="Delete" onClick={() => actions.onDelete(path)}>
            <Trash2 className="size-3.5" />
          </Button>
        </>
      )}
    </span>
  );
}

function parseValue(text: string): { ok: true; value: JsonValue } | { ok: false; error: string } {
  if (!text.trim()) return { ok: false, error: 'Enter a JSON value: "text", 42, true or { "key": "value" }.' };
  try {
    return { ok: true, value: JSON.parse(text) as JsonValue };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Invalid JSON" };
  }
}

/** Edit the value at a path (loaded in full) or add a child (a key, or a Firebase-made key with push). */
function ValueDialog({ source, edit, onClose, onSaved }: { source: DataSource; edit: Edit; onClose: () => void; onSaved: () => void }) {
  const { project } = useProjectContext();
  const toast = useToast();
  const isEdit = edit.mode === "edit";
  const full = useQuery({
    queryKey: ["projects", project.id, "rtdb", source.id, edit.path, "full"],
    queryFn: () => api.rtdb.read(project.id, source.id, edit.path),
    enabled: isEdit,
    gcTime: 0,
  });
  const [text, setText] = useState<string | null>(null);
  const [key, setKey] = useState("");
  const shown = text ?? (isEdit && full.data ? pretty(full.data.value) : "");
  const parsed = parseValue(shown);
  const keyOk = key === "" || isRtdbKey(key);
  const save = useMutation({
    mutationFn: async (): Promise<string> => {
      if (!parsed.ok) return "Nothing saved.";
      if (isEdit) {
        await api.rtdb.set(project.id, source.id, edit.path, parsed.value);
        return "Saved.";
      }
      if (key) {
        await api.rtdb.set(project.id, source.id, childPath(edit.path, key), parsed.value);
        return `Added /${childPath(edit.path, key)}.`;
      }
      const out = await api.rtdb.push(project.id, source.id, edit.path, parsed.value);
      return `Added /${childPath(out.path, out.key)}.`;
    },
    onSuccess: (message) => {
      toast.success(message);
      onSaved();
    },
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title={isEdit ? `Edit /${edit.path}` : `Add under /${edit.path}`}
      description={
        isEdit
          ? "The value at this path as JSON. Saving replaces it (and everything under it) with what is here."
          : "Leave the key empty to let Firebase make one (time-ordered, like -Nx3…: good for lists such as messages)."
      }
      size="lg"
      dismissible={!save.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} disabled={!parsed.ok || !keyOk || (isEdit && !full.data)} onClick={() => save.mutate()}>
            {isEdit ? "Save" : "Add"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {!isEdit && (
          <Field label="Key" optional error={keyOk ? undefined : "Keys can't contain . $ # [ ] /"}>
            {(id) => <Input id={id} value={key} onChange={(e) => setKey(e.target.value)} spellCheck={false} autoCapitalize="off" className="font-mono" />}
          </Field>
        )}
        {isEdit && full.isPending ? (
          <p className="text-sm text-muted">Loading the value…</p>
        ) : isEdit && full.isError ? (
          <Alert tone="danger">{errorMessage(full.error)}</Alert>
        ) : (
          <Field label="Value (JSON)" error={shown && !parsed.ok ? parsed.error : undefined}>
            {(id) => (
              <Textarea
                id={id}
                value={shown}
                onChange={(e) => setText(e.target.value)}
                rows={14}
                spellCheck={false}
                placeholder='{ "name": "Ann", "age": 31 }'
                className="font-mono text-xs"
              />
            )}
          </Field>
        )}
        {save.error && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
      </div>
    </Dialog>
  );
}
