import { useId } from "react";
import { cn } from "../../lib/cn";
import { parseJsonObject, pretty } from "./json";

export function JsonEditor({
  label,
  value,
  onChange,
  allowEmpty = false,
  rows = 12,
  hint,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  allowEmpty?: boolean;
  rows?: number;
  hint?: string;
  placeholder?: string;
}) {
  const id = useId();
  const result = parseJsonObject(value, { allowEmpty });
  const showError = !result.ok && value.trim().length > 0;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        <button
          type="button"
          className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
          disabled={!result.ok || result.value === null}
          onClick={() => result.ok && result.value && onChange(pretty(result.value))}
        >
          Format
        </button>
      </div>
      <textarea
        id={id}
        rows={rows}
        value={value}
        placeholder={placeholder}
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        aria-invalid={showError}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Tab" && !e.shiftKey) {
            e.preventDefault();
            const t = e.currentTarget;
            const { selectionStart: s, selectionEnd: end } = t;
            const next = value.slice(0, s) + "  " + value.slice(end);
            onChange(next);
            requestAnimationFrame(() => t.setSelectionRange(s + 2, s + 2));
          }
        }}
        className={cn(
          "w-full rounded-lg border bg-surface-2 px-3 py-2 font-mono text-xs leading-5 text-fg focus:ring-3 focus:ring-ring focus:outline-none sm:text-[13px]",
          showError ? "border-danger" : "border-border focus:border-accent",
        )}
      />
      {showError ? (
        <p className="text-xs text-danger">{!result.ok ? result.error : ""}</p>
      ) : hint ? (
        <p className="text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  );
}
