import { useMemo, type ReactNode } from "react";
import { Dialog } from "../../components/ui/Dialog";
import { cn } from "../../lib/cn";
import { diffStats, lineDiff } from "./diff";

const KIND = {
  same: { mark: " ", cls: "" },
  add: { mark: "+", cls: "bg-success-soft text-success" },
  del: { mark: "-", cls: "bg-danger-soft text-danger" },
};

/** Line diff from `a` to `b` (QUERY_EDITOR.md → phase 2): monospace, +/- gutter, green/red rows. */
export function DiffView({ a, b, className }: { a: string; b: string; className?: string }) {
  const diff = useMemo(() => lineDiff(a, b), [a, b]);
  if (diff === null) return <p className="text-sm text-muted">Too large to diff.</p>;
  const stats = diffStats(diff);
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <p className="text-xs text-muted tabular-nums">
        {stats.add === 0 && stats.del === 0 ? "No differences." : `+${stats.add} −${stats.del}`}
      </p>
      <pre className="max-h-[60vh] overflow-auto rounded-lg border border-border bg-surface-2 font-mono text-xs">
        {diff.map((l, i) => (
          <div key={i} className={cn("flex", KIND[l.kind].cls)}>
            <span className="w-6 shrink-0 text-center select-none" aria-hidden="true">
              {KIND[l.kind].mark}
            </span>
            <span className="whitespace-pre-wrap break-all">{l.text}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}

/** A dialog around one diff; the caller supplies the actions (Reload / Keep mine / Close …). */
export function DiffDialog({
  open,
  onClose,
  title,
  description,
  a,
  b,
  footer,
  loading = false,
  status,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  a: string;
  b: string;
  footer: ReactNode;
  loading?: boolean;
  /** Shown instead of the diff while one side is still being fetched (or failed to). */
  status?: ReactNode;
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title} description={description} size="lg" dismissible={!loading} footer={footer}>
      {status ?? (open && <DiffView a={a} b={b} />)}
    </Dialog>
  );
}
