import type { ReactNode } from "react";
import { Check } from "lucide-react";
import { cn } from "../../lib/cn";
import { Badge } from "./Badge";

export type StepStatus = "done" | "current" | "todo";

/**
 * One collapsible step of a guided setup (Cloudflare, sign-in apps). Open while it's the current step; the user can
 * open any other one. `open` forces it open, e.g. to keep a form visible once everything is done.
 */
export function StepCard({
  n,
  title,
  status,
  summary,
  open,
  children,
}: {
  n: number;
  title: ReactNode;
  status: StepStatus;
  summary?: ReactNode;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details open={open ?? status === "current"} className="group rounded-xl border border-border bg-surface open:shadow-xs">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-3 select-none sm:px-4 [&::-webkit-details-marker]:hidden">
        <span
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
            status === "done" && "border-accent bg-accent text-accent-fg",
            status === "current" && "border-accent bg-surface text-accent",
            status === "todo" && "border-border bg-surface text-muted",
          )}
          aria-hidden="true"
        >
          {status === "done" ? <Check className="size-4" /> : n}
        </span>
        <span className="min-w-0 flex-1">
          <span className={cn("block font-semibold", status === "todo" && "text-muted")}>
            <span className="sr-only">Step {n}, {status === "done" ? "done" : status === "current" ? "current step" : "to do"}: </span>
            {title}
          </span>
          {summary && <span className="block truncate text-xs text-muted">{summary}</span>}
        </span>
        <Badge tone={status === "done" ? "success" : status === "current" ? "accent" : "neutral"}>
          {status === "done" ? "Done" : status === "current" ? "Now" : "To do"}
        </Badge>
      </summary>
      <div className="border-t border-border px-3 py-3 text-sm sm:px-4">{children}</div>
    </details>
  );
}
