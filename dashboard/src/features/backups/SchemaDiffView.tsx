import { useState } from "react";
import { ChevronRight, FileJson, Minus, Plus, Table2, TriangleAlert } from "lucide-react";
import type { DiffChange, FieldDiff, SchemaDiff, SchemaDiffEntity } from "../../api/types";
import { Badge, type BadgeTone } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import {
  CHANGE_LABELS,
  fieldAttributeChanges,
  fieldSummary,
  isDataOnlyChange,
  rowCountDelta,
  sortDiffEntities,
  summarizeDiff,
} from "./diff";

const CHANGE_TONES: Record<DiffChange, BadgeTone> = { added: "success", removed: "danger", changed: "warning" };

function ChangeBadge({ change }: { change: DiffChange }) {
  return <Badge tone={CHANGE_TONES[change]}>{CHANGE_LABELS[change]}</Badge>;
}

const rowTone = { neutral: "text-muted", success: "text-success", danger: "text-danger" };

/** Readable rendering of a SchemaDiff (entities, fields with before/after, indexes, validators, rows). */
export function SchemaDiffView({ diff, entityNoun = "table" }: { diff: SchemaDiff; entityNoun?: "table" | "collection" }) {
  const summary = summarizeDiff(diff);
  const sorted = sortDiffEntities(diff.entities);
  const structural = sorted.filter((e) => !isDataOnlyChange(e));
  const dataOnly = sorted.filter(isDataOnlyChange);

  if (summary.empty) {
    return (
      <EmptyState
        title="No differences"
        description={`The ${entityNoun}s, fields, indexes and row counts are the same in both versions.`}
      />
    );
  }

  const chip = (n: number, label: string, tone: BadgeTone) =>
    n > 0 ? (
      <Badge tone={tone}>
        {n} {label}
      </Badge>
    ) : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5" aria-label="Summary of changes">
        {chip(summary.entities.added, `${entityNoun}${summary.entities.added === 1 ? "" : "s"} added`, "success")}
        {chip(summary.entities.removed, `${entityNoun}${summary.entities.removed === 1 ? "" : "s"} removed`, "danger")}
        {(() => {
          const n = structural.filter((e) => e.change === "changed").length;
          return chip(n, `${entityNoun}${n === 1 ? "" : "s"} changed`, "warning");
        })()}
        {chip(summary.fields.added + summary.fields.removed + summary.fields.changed, "field changes", "neutral")}
        {chip(summary.indexes, "index changes", "neutral")}
        {chip(summary.validators, "validator changes", "neutral")}
        {chip(summary.rowChanges, "row count changes", "info")}
      </div>

      <ul className="space-y-3">
        {structural.map((e) => (
          <li key={e.name}>
            <EntityDiffCard entity={e} entityNoun={entityNoun} />
          </li>
        ))}
      </ul>

      {dataOnly.length > 0 && (
        <section className="rounded-xl border border-border">
          <h4 className="border-b border-border px-3 py-2 text-sm font-semibold">Row counts only</h4>
          <ul className="divide-y divide-border text-sm">
            {dataOnly.map((e) => {
              const delta = rowCountDelta(e.row_count);
              return (
                <li key={e.name} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                  <span className="font-mono">{e.name}</span>
                  {delta && <span className={cn("tabular-nums", rowTone[delta.tone])}>{delta.text}</span>}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

function EntityDiffCard({ entity, entityNoun }: { entity: SchemaDiffEntity; entityNoun: string }) {
  const [open, setOpen] = useState(entity.change === "changed" || entity.fields.length <= 8);
  const delta = rowCountDelta(entity.row_count);
  const Icon = entityNoun === "collection" ? FileJson : Table2;
  const hasDetails = entity.fields.length > 0 || entity.indexes.length > 0 || entity.validator_changed;
  return (
    <article
      className={cn(
        "overflow-hidden rounded-xl border",
        entity.change === "added" && "border-success/40",
        entity.change === "removed" && "border-danger/40",
        entity.change === "changed" && "border-border",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        disabled={!hasDetails}
        className="flex w-full flex-wrap items-center gap-2 bg-surface-2/60 px-3 py-2 text-left disabled:cursor-default"
      >
        {hasDetails && <ChevronRight className={cn("size-4 shrink-0 text-muted transition-transform", open && "rotate-90")} />}
        <Icon className="size-4 shrink-0 text-muted" />
        <span className={cn("min-w-0 truncate font-mono text-sm font-semibold", entity.change === "removed" && "line-through")}>
          {entity.name}
        </span>
        <ChangeBadge change={entity.change} />
        {delta && <span className={cn("ml-auto text-xs tabular-nums", rowTone[delta.tone])}>{delta.text}</span>}
      </button>
      {open && hasDetails && (
        <div className="space-y-3 px-3 py-3">
          {entity.fields.length > 0 && <FieldDiffTable fields={entity.fields} />}
          {entity.indexes.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-semibold text-muted uppercase">Indexes</p>
              <ul className="flex flex-wrap gap-1.5">
                {entity.indexes.map((ix) => (
                  <li key={ix.name}>
                    <Badge tone={CHANGE_TONES[ix.change]}>
                      {ix.change === "added" ? <Plus className="size-3" /> : ix.change === "removed" ? <Minus className="size-3" /> : null}
                      <span className="font-mono">{ix.name}</span>
                      {ix.change === "changed" && " (changed)"}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {entity.validator_changed && (
            <p className="flex items-center gap-1.5 text-xs text-warning">
              <TriangleAlert className="size-3.5" /> The document validator ($jsonSchema) changed.
            </p>
          )}
        </div>
      )}
    </article>
  );
}

function FieldDiffTable({ fields }: { fields: FieldDiff[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse text-left text-xs">
        <thead className="text-muted">
          <tr>
            <th className="py-1 pr-2 font-semibold">Field</th>
            <th className="py-1 pr-2 font-semibold">Change</th>
            <th className="py-1 pr-2 font-semibold">Before</th>
            <th className="py-1 font-semibold">After</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border align-top">
          {fields.map((f) => {
            const attrs = fieldAttributeChanges(f.before, f.after);
            return (
              <tr key={f.name}>
                <td className="py-1.5 pr-2 font-mono font-medium">{f.name}</td>
                <td className="py-1.5 pr-2">
                  <ChangeBadge change={f.change} />
                </td>
                {f.change === "changed" && attrs.length > 0 ? (
                  <>
                    <td className="py-1.5 pr-2">
                      <ul className="space-y-0.5">
                        {attrs.map((a) => (
                          <li key={a.attribute}>
                            <span className="text-muted">{a.attribute}: </span>
                            <span className="rounded bg-danger-soft px-1 font-mono">{a.before}</span>
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td className="py-1.5">
                      <ul className="space-y-0.5">
                        {attrs.map((a) => (
                          <li key={a.attribute}>
                            <span className="text-muted">{a.attribute}: </span>
                            <span className="rounded bg-success-soft px-1 font-mono">{a.after}</span>
                          </li>
                        ))}
                      </ul>
                    </td>
                  </>
                ) : (
                  <>
                    <td className="py-1.5 pr-2 font-mono text-muted">{f.before ? fieldSummary(f.before) : "—"}</td>
                    <td className="py-1.5 font-mono">{f.after ? fieldSummary(f.after) : "—"}</td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
