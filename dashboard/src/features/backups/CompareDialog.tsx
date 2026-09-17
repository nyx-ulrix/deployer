import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Columns2, ListTree } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import type { Backup, DataSource } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { ErrorState } from "../../components/ui/States";
import { Tabs } from "../../components/ui/Tabs";
import { formatDateTime, localTimeZone } from "../../lib/format";
import { SchemaDiffView } from "./SchemaDiffView";
import { TRIGGER_LABELS } from "./timeline";

const SchemaCompareDiagrams = lazy(() => import("./SchemaCompareDiagrams"));

const CURRENT = "current";

function versionLabel(b: Backup): string {
  return `${formatDateTime(b.started_at)} · ${b.label ?? TRIGGER_LABELS[b.trigger]}`;
}

type View = "diff" | "diagrams";

export function CompareDialog({
  projectId,
  source,
  backups,
  initialFrom,
  onClose,
}: {
  projectId: string;
  source: DataSource;
  backups: Backup[];
  initialFrom: string;
  onClose: () => void;
}) {
  const versions = backups.filter((b) => b.status === "succeeded");
  const [from, setFrom] = useState(initialFrom);
  const [to, setTo] = useState<string>(CURRENT);
  const [view, setView] = useState<View>("diff");

  const labelFor = (id: string) =>
    id === CURRENT ? "Current database" : (versions.find((b) => b.id === id) ? versionLabel(versions.find((b) => b.id === id) as Backup) : id);

  const diff = useQuery({
    queryKey: qk.backupDiff(projectId, source.id, from, to),
    queryFn: () => api.backups.diff(projectId, source.id, from, to),
    enabled: from !== to,
    staleTime: 60_000,
  });

  const options = (exclude: string) => (
    <>
      {versions.map((b) => (
        <option key={b.id} value={b.id} disabled={b.id === exclude}>
          {versionLabel(b)}
        </option>
      ))}
    </>
  );

  return (
    <Dialog
      open
      onClose={onClose}
      size="xl"
      title={`Compare versions — ${source.name}`}
      description={`Times in ${localTimeZone()}.`}
      footer={<Button onClick={onClose}>Close</Button>}
    >
      <div className="space-y-4">
        <div className="grid items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
          <Field label="From">
            {(id) => (
              <Select id={id} value={from} onChange={(e) => setFrom(e.target.value)}>
                {options(to)}
              </Select>
            )}
          </Field>
          <ArrowRight className="mx-auto hidden size-4 text-muted sm:mb-3 sm:block" aria-hidden="true" />
          <Field label="To">
            {(id) => (
              <Select id={id} value={to} onChange={(e) => setTo(e.target.value)}>
                <option value={CURRENT}>Current database (live)</option>
                {options(from)}
              </Select>
            )}
          </Field>
        </div>

        <Tabs<View>
          value={view}
          onChange={setView}
          items={[
            { value: "diff", label: "Changes", icon: <ListTree className="size-3.5" /> },
            { value: "diagrams", label: "Side by side", icon: <Columns2 className="size-3.5" /> },
          ]}
        />

        {from === to ? (
          <p className="text-sm text-muted">Pick two different versions.</p>
        ) : view === "diff" ? (
          diff.isPending ? (
            <PageSpinner label="Comparing…" />
          ) : diff.isError ? (
            <ErrorState error={diff.error} onRetry={() => void diff.refetch()} />
          ) : (
            <SchemaDiffView diff={diff.data} entityNoun={source.kind === "sql" ? "table" : "collection"} />
          )
        ) : (
          <Suspense fallback={<PageSpinner label="Loading diagrams…" />}>
            <SchemaCompareDiagrams
              projectId={projectId}
              sourceId={source.id}
              from={{ backupId: from, label: labelFor(from) }}
              to={{ backupId: to, label: labelFor(to) }}
              diff={diff.data}
            />
          </Suspense>
        )}
      </div>
    </Dialog>
  );
}
