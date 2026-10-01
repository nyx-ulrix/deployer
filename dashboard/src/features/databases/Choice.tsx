import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/** A selectable card: icon, title and one plain sentence (Add database dialog). */
export function Choice({
  selected,
  onClick,
  icon,
  title,
  description,
  tone,
  disabled,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  icon: ReactNode;
  title: string;
  description: string;
  tone?: "sql" | "nosql";
  disabled?: boolean;
  children?: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      disabled={disabled}
      className={cn(
        "flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        selected ? "border-accent bg-accent-soft/50 ring-1 ring-accent" : "border-border hover:bg-surface-2",
      )}
    >
      <span
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-lg",
          tone === "sql" ? "bg-sql-soft text-sql" : tone === "nosql" ? "bg-nosql-soft text-nosql" : "bg-surface-2 text-accent",
        )}
      >
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold">{title}</span>
        <span className="mt-0.5 block text-xs text-muted">{description}</span>
        {children}
      </span>
    </button>
  );
}
