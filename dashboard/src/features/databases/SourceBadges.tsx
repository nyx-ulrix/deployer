import { Database, Leaf } from "lucide-react";
import type { DataSource } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { engineLabel } from "../../lib/format";

export function KindBadge({ kind }: { kind: DataSource["kind"] }) {
  return kind === "sql" ? (
    <Badge tone="sql">
      <Database className="size-3" /> SQL
    </Badge>
  ) : (
    <Badge tone="nosql">
      <Leaf className="size-3" /> NoSQL
    </Badge>
  );
}

export function EngineBadge({ engine }: { engine: string }) {
  return <Badge>{engineLabel(engine)}</Badge>;
}

export function ModeBadge({ mode, cloud }: { mode: DataSource["mode"]; cloud?: DataSource["cloud"] }) {
  if (cloud) {
    // docs/CLOUD.md "C2": in the user's own AWS account or Firebase project.
    return (
      <Badge tone="info" title={cloud.when_pc_off}>
        {cloud.provider === "firebase" ? "Firebase" : "AWS"}
        {cloud.region ? ` · ${cloud.region}` : ""}
      </Badge>
    );
  }
  return <Badge tone={mode === "managed" ? "accent" : "info"}>{mode === "managed" ? "Managed" : "External"}</Badge>;
}

export function StatusBadge({ status, message }: { status: DataSource["status"]; message?: string | null }) {
  const tone = status === "ok" ? "success" : status === "error" ? "danger" : "neutral";
  const label = status === "ok" ? "Healthy" : status === "error" ? "Error" : status === "creating" ? "Creating" : "Unknown";
  return (
    <Badge tone={tone} title={message ?? undefined}>
      <span
        className={
          "size-1.5 rounded-full " +
          (status === "ok" ? "bg-success" : status === "error" ? "bg-danger" : "bg-muted")
        }
      />
      {label}
    </Badge>
  );
}
