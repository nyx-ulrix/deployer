import { useState } from "react";
import { ClipboardPaste, Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Input, Textarea } from "../../components/ui/Input";
import { cn } from "../../lib/cn";
import { parseEnv, type EnvRow } from "./deploys";

/** Key/value rows plus a "paste .env" box; `secret` masks values with a per-row reveal; `required` keys without a value are highlighted. */
export function EnvEditor({
  rows,
  onChange,
  secret = false,
  disabled = false,
  required = [],
}: {
  rows: EnvRow[];
  onChange: (rows: EnvRow[]) => void;
  secret?: boolean;
  disabled?: boolean;
  required?: string[];
}) {
  const [pasting, setPasting] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [shown, setShown] = useState<Set<number>>(new Set());

  const update = (i: number, patch: Partial<EnvRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const remove = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const toggle = (i: number) =>
    setShown((s) => {
      const next = new Set(s);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  const applyPaste = () => {
    const parsed = parseEnv(pasteText);
    // Pasted keys replace existing ones of the same name, in place.
    const byKey = new Map(parsed.map((r) => [r.key, r.value]));
    const merged = rows.map((r) => (byKey.has(r.key) ? { ...r, value: byKey.get(r.key) as string } : r));
    const existing = new Set(rows.map((r) => r.key));
    for (const r of parsed) if (!existing.has(r.key)) merged.push(r);
    onChange(merged);
    setPasteText("");
    setPasting(false);
  };

  return (
    <div className="space-y-2">
      {rows.length === 0 && !pasting && <p className="text-xs text-muted">No variables yet.</p>}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <Input
            value={r.key}
            onChange={(e) => update(i, { key: e.target.value })}
            placeholder="KEY"
            aria-label={`Variable ${i + 1} name`}
            className="h-9 font-mono text-xs sm:text-xs"
            autoCapitalize="off"
            spellCheck={false}
            disabled={disabled}
          />
          <Input
            type={secret && !shown.has(i) ? "password" : "text"}
            value={r.value}
            onChange={(e) => update(i, { value: e.target.value })}
            placeholder={required.includes(r.key) ? "fill in" : "value"}
            aria-label={`Variable ${i + 1} value`}
            className={cn("h-9 font-mono text-xs sm:text-xs", required.includes(r.key) && !r.value && "border-warning bg-warning-soft/40")}
            autoCapitalize="off"
            spellCheck={false}
            disabled={disabled}
          />
          {secret && (
            <Button size="icon-sm" variant="ghost" onClick={() => toggle(i)} aria-label={shown.has(i) ? "Hide value" : "Reveal value"}>
              {shown.has(i) ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </Button>
          )}
          <Button size="icon-sm" variant="ghost" onClick={() => remove(i)} aria-label="Remove variable" disabled={disabled}>
            <Trash2 className="size-4" />
          </Button>
        </div>
      ))}
      {pasting ? (
        <div className="space-y-2">
          <Textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={"# paste a .env file\nAPI_URL=https://…\nSECRET=\"…\""}
            className="font-mono text-xs sm:text-xs"
            spellCheck={false}
            data-autofocus
          />
          <div className="flex gap-2">
            <Button size="sm" variant="primary" onClick={applyPaste} disabled={!pasteText.trim()}>
              Add {parseEnv(pasteText).length || ""} variables
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPasting(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => onChange([...rows, { key: "", value: "" }])} disabled={disabled}>
            Add variable
          </Button>
          <Button size="sm" variant="ghost" icon={<ClipboardPaste className="size-3.5" />} onClick={() => setPasting(true)} disabled={disabled}>
            Paste .env
          </Button>
        </div>
      )}
    </div>
  );
}
