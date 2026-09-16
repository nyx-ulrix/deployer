import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export type BadgeTone =
  | "neutral"
  | "accent"
  | "success"
  | "danger"
  | "warning"
  | "info"
  | "sql"
  | "nosql"
  | "link";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-muted border-border",
  accent: "bg-accent-soft text-accent border-transparent",
  success: "bg-success-soft text-success border-transparent",
  danger: "bg-danger-soft text-danger border-transparent",
  warning: "bg-warning-soft text-warning border-transparent",
  info: "bg-info-soft text-info border-transparent",
  sql: "bg-sql-soft text-sql border-transparent",
  nosql: "bg-nosql-soft text-nosql border-transparent",
  link: "bg-surface-2 text-link border-transparent",
};

export function Badge({
  tone = "neutral",
  children,
  className,
  title,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] leading-4 font-semibold whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
