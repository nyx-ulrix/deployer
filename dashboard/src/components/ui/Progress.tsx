import { cn } from "../../lib/cn";

const barTones = {
  accent: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  muted: "bg-muted",
};

/** Horizontal bar; `value` is 0–100, or null for an indeterminate (pulsing) bar. */
export function ProgressBar({
  value,
  tone = "accent",
  label,
  className,
}: {
  value: number | null;
  tone?: keyof typeof barTones;
  label: string;
  className?: string;
}) {
  const v = value === null ? null : Math.min(100, Math.max(0, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={v === null ? undefined : Math.round(v)}
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-surface-2", className)}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-500", barTones[tone], v === null && "w-1/3 animate-pulse")}
        style={v === null ? undefined : { width: `${v}%` }}
      />
    </div>
  );
}

/** Small online/offline indicator dot. */
export function StatusDot({
  tone,
  pulse = false,
  className,
}: {
  tone: "success" | "danger" | "warning" | "muted";
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative inline-flex size-2 shrink-0", className)} aria-hidden="true">
      {pulse && <span className={cn("absolute inset-0 animate-ping rounded-full opacity-60", barTones[tone])} />}
      <span className={cn("relative inline-flex size-2 rounded-full", barTones[tone])} />
    </span>
  );
}
