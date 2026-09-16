import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, Info } from "lucide-react";
import type { ConventionIssue, SourceSchema } from "../../api/types";
import { cn } from "../../lib/cn";
import { ruleInfo } from "./conventions";

export function ConventionsPanel({
  issues,
  sources,
  onFocus,
}: {
  issues: ConventionIssue[];
  sources: SourceSchema[];
  onFocus: (issue: ConventionIssue) => void;
}) {
  const [openRule, setOpenRule] = useState<string | null>(null);
  const sourceName = (id: string | null) => sources.find((s) => s.source_id === id)?.name;

  if (issues.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-muted">
        <CheckCircle2 className="size-6 text-success" />
        <p>No convention issues. Nice schema!</p>
      </div>
    );
  }

  const groups: { severity: ConventionIssue["severity"]; label: string; items: ConventionIssue[] }[] = [
    { severity: "warning", label: "Warnings", items: issues.filter((i) => i.severity === "warning") },
    { severity: "info", label: "Suggestions", items: issues.filter((i) => i.severity === "info") },
  ];

  return (
    <div className="space-y-4 p-3">
      <p className="text-xs text-muted">
        Checks against Deployer's database planning conventions. They never block anything.
      </p>
      {groups
        .filter((g) => g.items.length > 0)
        .map((g) => (
          <section key={g.severity}>
            <h3
              className={cn(
                "mb-1.5 flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase",
                g.severity === "warning" ? "text-warning" : "text-info",
              )}
            >
              {g.severity === "warning" ? <AlertTriangle className="size-3.5" /> : <Info className="size-3.5" />}
              {g.label} ({g.items.length})
            </h3>
            <ul className="space-y-1.5">
              {g.items.map((issue, i) => {
                const info = ruleInfo(issue.rule);
                const key = `${issue.rule}-${i}`;
                const expanded = openRule === key;
                const location = [
                  sourceName(issue.source_id),
                  issue.entity && (issue.field ? `${issue.entity}.${issue.field}` : issue.entity),
                ]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <li key={key} className="rounded-lg border border-border bg-surface">
                    <div className="flex items-start gap-2 p-2">
                      <button
                        type="button"
                        onClick={() => setOpenRule(expanded ? null : key)}
                        aria-expanded={expanded}
                        title={`${issue.rule}: ${info.title}`}
                        className={cn(
                          "mt-0.5 inline-flex shrink-0 items-center gap-0.5 rounded px-1 font-mono text-[11px] font-bold underline decoration-dotted underline-offset-2",
                          g.severity === "warning" ? "bg-warning-soft text-warning" : "bg-info-soft text-info",
                        )}
                      >
                        {issue.rule}
                        <ChevronDown className={cn("size-3 transition-transform", expanded && "rotate-180")} />
                      </button>
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left text-sm disabled:cursor-default"
                        disabled={!issue.entity}
                        onClick={() => onFocus(issue)}
                      >
                        <span className="block">{issue.message}</span>
                        {location && (
                          <span className="mt-0.5 block truncate font-mono text-[11px] text-muted hover:text-accent">
                            {location}
                          </span>
                        )}
                      </button>
                    </div>
                    {expanded && (
                      <div className="border-t border-border px-2 py-1.5 text-xs text-muted">
                        <span className="font-semibold text-fg">{info.title}.</span> {info.description}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
    </div>
  );
}
