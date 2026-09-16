import { useEffect, useState } from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { cn } from "../../lib/cn";
import { copyText } from "../../lib/clipboard";

export function CopyButton({ value, className, label = "Copy" }: { value: string; className?: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);
  return (
    <button
      type="button"
      onClick={async () => setCopied(await copyText(value))}
      className={cn(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg",
        className,
      )}
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
    >
      {copied ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
    </button>
  );
}

export function CopyField({
  label,
  value,
  secret = false,
  className,
  mono = true,
}: {
  label?: string;
  value: string;
  secret?: boolean;
  className?: string;
  mono?: boolean;
}) {
  const [revealed, setRevealed] = useState(!secret);
  return (
    <div className={cn("min-w-0", className)}>
      {label && <div className="mb-1 text-xs font-medium text-muted">{label}</div>}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-surface-2 py-1 pr-1 pl-3">
        <code className={cn("min-w-0 flex-1 truncate text-sm", mono ? "font-mono" : "")} title={revealed ? value : undefined}>
          {revealed ? value || "—" : "•".repeat(Math.min(24, Math.max(8, value.length)))}
        </code>
        {secret && (
          <button
            type="button"
            onClick={() => setRevealed((r) => !r)}
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface hover:text-fg"
            aria-label={revealed ? "Hide" : "Reveal"}
            title={revealed ? "Hide" : "Reveal"}
          >
            {revealed ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        )}
        <CopyButton value={value} label={label ? `Copy ${label}` : "Copy"} />
      </div>
    </div>
  );
}
