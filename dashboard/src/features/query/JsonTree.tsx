import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { JsonValue } from "../../api/types";
import { cn } from "../../lib/cn";
import { ejsonLeaf } from "./results";

const PAGE = 100;
const INDENT = 14;

/** Collapsible JSON tree; the first two levels start open, long arrays/objects are revealed in pages. */
export function JsonTree({ value, className }: { value: JsonValue; className?: string }) {
  return (
    <div className={cn("font-mono text-xs leading-5", className)}>
      <Node value={value} depth={0} />
    </div>
  );
}

function Key({ name, index }: { name: string | undefined; index: boolean }) {
  if (name === undefined) return null;
  return (
    <span className="shrink-0">
      <span className={index ? "text-muted" : "text-fg"}>{name}</span>
      <span className="text-muted">: </span>
    </span>
  );
}

function Leaf({ value, leaf }: { value: JsonValue; leaf: string | null }) {
  if (leaf !== null) return <span className="break-all text-info">{leaf}</span>;
  if (value === null) return <span className="text-muted italic">null</span>;
  if (typeof value === "string") return <span className="break-all whitespace-pre-wrap text-success">{JSON.stringify(value)}</span>;
  if (typeof value === "number") return <span className="text-sql tabular-nums">{String(value)}</span>;
  if (typeof value === "boolean") return <span className="text-warning">{String(value)}</span>;
  return <span className="text-muted">{Array.isArray(value) ? "[]" : "{}"}</span>;
}

function Node({ name, value, depth, index = false }: { name?: string; value: JsonValue; depth: number; index?: boolean }) {
  const [open, setOpen] = useState(depth < 2);
  const [shown, setShown] = useState(PAGE);
  const leaf = ejsonLeaf(value);
  const isArray = Array.isArray(value);
  const entries: [string, JsonValue][] =
    leaf === null && typeof value === "object" && value !== null
      ? isArray
        ? value.map((v, i): [string, JsonValue] => [String(i), v])
        : Object.entries(value)
      : [];
  const container = leaf === null && typeof value === "object" && value !== null && entries.length > 0;

  if (!container) {
    return (
      <div className="flex gap-0.5" style={{ paddingLeft: depth * INDENT + 16 }}>
        <Key name={name} index={index} />
        <Leaf value={value} leaf={leaf} />
      </div>
    );
  }

  const count = entries.length;
  const summary = `${count} ${isArray ? (count === 1 ? "item" : "items") : count === 1 ? "key" : "keys"}`;
  const openBracket = isArray ? "[" : "{";
  const closeBracket = isArray ? "]" : "}";

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-0.5 rounded text-left hover:bg-surface-2"
        style={{ paddingLeft: depth * INDENT }}
      >
        {open ? (
          <ChevronDown className="size-3.5 shrink-0 text-muted" />
        ) : (
          <ChevronRight className="size-3.5 shrink-0 text-muted" />
        )}
        <Key name={name} index={index} />
        <span className="text-muted">
          {openBracket}
          {!open && ` ${summary} ${closeBracket}`}
        </span>
        {open && <span className="ml-2 text-[10px] text-muted">{summary}</span>}
      </button>
      {open && (
        <>
          {entries.slice(0, shown).map(([k, v]) => (
            <Node key={k} name={k} value={v} depth={depth + 1} index={isArray} />
          ))}
          {count > shown && (
            <button
              type="button"
              onClick={() => setShown((s) => s + PAGE)}
              className="text-accent hover:underline"
              style={{ paddingLeft: (depth + 1) * INDENT + 16 }}
            >
              … {count - shown} more
            </button>
          )}
          <div className="text-muted" style={{ paddingLeft: depth * INDENT + 16 }}>
            {closeBracket}
          </div>
        </>
      )}
    </div>
  );
}
