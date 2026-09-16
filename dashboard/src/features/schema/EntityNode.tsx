import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { AlertTriangle, FileJson, Table2 } from "lucide-react";
import type { Field } from "../../api/types";
import { cn } from "../../lib/cn";
import { engineLabel, formatNumber } from "../../lib/format";
import { ENTITY_HANDLE, type EntityFlowNode, type SourceGroupFlowNode } from "./flow-types";
import { HEADER_HEIGHT, NODE_WIDTH, ROW_HEIGHT, handleId } from "./graph";

function FlagBadge({ children, className, title }: { children: string; className: string; title: string }) {
  return (
    <span title={title} className={cn("rounded px-1 text-[9px] leading-[14px] font-bold tracking-wide", className)}>
      {children}
    </span>
  );
}

function FieldFlags({ field }: { field: Field }) {
  return (
    <span className="flex shrink-0 gap-0.5">
      {field.primary_key && (
        <FlagBadge title="Primary key" className="bg-warning-soft text-warning">
          PK
        </FlagBadge>
      )}
      {field.foreign_key && (
        <FlagBadge
          title={`Foreign key → ${field.foreign_key.entity}.${field.foreign_key.field}`}
          className="bg-sql-soft text-sql"
        >
          FK
        </FlagBadge>
      )}
      {field.unique && !field.primary_key && (
        <FlagBadge title="Unique" className="bg-accent-soft text-accent">
          UQ
        </FlagBadge>
      )}
      {!field.nullable && !field.primary_key && (
        <FlagBadge title="Not null" className="bg-surface-2 text-muted">
          NN
        </FlagBadge>
      )}
      {field.indexed && !field.unique && !field.primary_key && (
        <FlagBadge title="Indexed" className="bg-info-soft text-info">
          IDX
        </FlagBadge>
      )}
    </span>
  );
}

const handleStyle = { top: "50%" } as const;

function EntityNodeImpl({ data, selected }: NodeProps<EntityFlowNode>) {
  const { entity, source, issueFields, issueCount, highlight, dimmed, focusField } = data;
  const isSql = source.kind === "sql";
  const Icon = isSql ? Table2 : FileJson;

  return (
    <div
      className={cn(
        "erd-node overflow-hidden rounded-xl border bg-surface shadow-md transition-opacity",
        selected ? "border-accent" : "border-border-strong",
        highlight && "highlight",
        dimmed && "opacity-40",
      )}
      style={{ width: NODE_WIDTH }}
    >
      <div
        className={cn(
          "relative flex items-center gap-2 border-b border-border px-2.5",
          isSql ? "border-t-4 border-t-sql bg-sql-soft" : "border-t-4 border-t-nosql bg-nosql-soft",
        )}
        style={{ height: HEADER_HEIGHT - 4 }}
      >
        <Handle type="source" position={Position.Left} id={`${ENTITY_HANDLE}|L`} className="field-handle" isConnectable={false} />
        <Handle type="source" position={Position.Right} id={`${ENTITY_HANDLE}|R`} className="field-handle" isConnectable={false} />
        <Icon className={cn("size-4 shrink-0", isSql ? "text-sql" : "text-nosql")} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[13px] leading-4 font-semibold text-fg" title={entity.name}>
            {entity.name}
          </div>
          <div className="truncate text-[10px] leading-3.5 text-muted">
            <span className={cn("font-semibold", isSql ? "text-sql" : "text-nosql")}>{engineLabel(source.engine)}</span>
            {" · "}
            {source.name}
            {entity.row_count !== null && ` · ${formatNumber(entity.row_count)} ${isSql ? "rows" : "docs"}`}
          </div>
        </div>
        {issueCount > 0 && (
          <span
            className="flex items-center gap-0.5 rounded-md bg-warning-soft px-1 text-[10px] font-semibold text-warning"
            title={`${issueCount} convention issue${issueCount === 1 ? "" : "s"}`}
          >
            <AlertTriangle className="size-3" />
            {issueCount}
          </span>
        )}
      </div>
      <div className="py-1">
        {entity.fields.length === 0 && (
          <div className="px-2.5 text-xs text-muted italic" style={{ height: ROW_HEIGHT, lineHeight: `${ROW_HEIGHT}px` }}>
            {isSql ? "No columns" : "No fields sampled"}
          </div>
        )}
        {entity.fields.map((f) => {
          const depth = f.name.split(".").length - 1;
          const leaf = depth > 0 ? f.name.slice(f.name.lastIndexOf(".") + 1) : f.name;
          const optional = f.occurrence !== null && f.occurrence < 1;
          const hasIssue = issueFields.includes(f.name);
          return (
            <div
              key={f.name}
              className={cn(
                "relative flex items-center gap-1.5 px-2.5 text-xs",
                focusField === f.name && "bg-accent-soft",
              )}
              style={{ height: ROW_HEIGHT }}
            >
              <Handle type="source" position={Position.Left} id={handleId(f.name, "L")} className="field-handle" style={handleStyle} isConnectable={false} />
              <Handle type="source" position={Position.Right} id={handleId(f.name, "R")} className="field-handle" style={handleStyle} isConnectable={false} />
              <span
                className={cn("max-w-[62%] shrink-0 truncate font-mono", f.primary_key ? "font-semibold text-fg" : "text-fg/90")}
                style={{ paddingLeft: depth * 10 }}
                title={f.name}
              >
                {depth > 0 && <span className="text-muted">↳ </span>}
                {leaf}
                {optional && (
                  <span
                    className="ml-0.5 font-bold text-warning"
                    title={`Present in ${Math.round((f.occurrence ?? 0) * 100)}% of sampled documents`}
                  >
                    ?
                  </span>
                )}
              </span>
              {hasIssue && <span className="size-1.5 shrink-0 rounded-full bg-warning" title="Convention issue" />}
              <span className="min-w-0 flex-1 truncate pl-1 text-right font-mono text-[11px] text-muted" title={f.data_type}>
                {f.data_type}
              </span>
              <FieldFlags field={f} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const EntityNode = memo(EntityNodeImpl);

function SourceGroupNodeImpl({ data }: NodeProps<SourceGroupFlowNode>) {
  const isSql = data.kind === "sql";
  return (
    <div
      className={cn(
        "pointer-events-none rounded-2xl border-2 border-dashed",
        isSql ? "border-sql/30 bg-sql-soft/25" : "border-nosql/30 bg-nosql-soft/25",
      )}
      style={{ width: data.width, height: data.height }}
    >
      <div
        className={cn(
          "px-4 pt-2 text-xs font-semibold tracking-wide uppercase",
          isSql ? "text-sql" : "text-nosql",
        )}
      >
        {data.label} · {engineLabel(data.engine)}
      </div>
    </div>
  );
}

export const SourceGroupNode = memo(SourceGroupNodeImpl);
