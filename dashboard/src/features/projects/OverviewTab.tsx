import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Database, KeyRound, Leaf, Network, Table2, Users } from "lucide-react";
import { useDataSources } from "../../api/hooks";
import { Card } from "../../components/ui/States";
import { Spinner } from "../../components/ui/Spinner";
import { formatDate } from "../../lib/format";
import { ROLE_DESCRIPTIONS, ROLE_LABELS } from "../../lib/roles";
import { EngineBadge, KindBadge, StatusBadge } from "../databases/SourceBadges";
import { useProjectContext } from "./project-context";

function QuickLink({ to, icon, title, description }: { to: string; icon: ReactNode; title: string; description: string }) {
  return (
    <Link
      to={to}
      className="group flex items-start gap-3 rounded-xl border border-border bg-surface p-4 shadow-xs transition-colors hover:border-accent"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-accent">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 font-medium">
          {title}
          <ArrowRight className="size-3.5 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
        </span>
        <span className="mt-0.5 block text-sm text-muted">{description}</span>
      </span>
    </Link>
  );
}

export function OverviewTab() {
  const { project, can } = useProjectContext();
  const sources = useDataSources(project.id);
  const base = `/projects/${project.id}`;
  const sqlCount = sources.data?.filter((s) => s.kind === "sql").length ?? project.data_source_counts.sql;
  const nosqlCount = sources.data?.filter((s) => s.kind === "nosql").length ?? project.data_source_counts.nosql;

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Card title="Summary">
          <p className="text-sm">{project.description || <span className="text-muted">No description.</span>}</p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted">Slug</dt>
              <dd className="truncate font-mono">{project.slug}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Created</dt>
              <dd>{formatDate(project.created_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Your role</dt>
              <dd title={ROLE_DESCRIPTIONS[project.my_role]}>{ROLE_LABELS[project.my_role]}</dd>
            </div>
          </dl>
        </Card>

        <Card
          title="Databases"
          description="A project can use SQL and NoSQL databases together."
          actions={
            <Link to={`${base}/databases`} className="text-sm font-medium text-accent hover:underline">
              Manage
            </Link>
          }
        >
          <div className="mb-4 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-sql-soft p-3">
              <div className="flex items-center gap-1.5 text-xs font-medium text-sql">
                <Database className="size-3.5" /> SQL
              </div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">{sqlCount}</div>
            </div>
            <div className="rounded-xl bg-nosql-soft p-3">
              <div className="flex items-center gap-1.5 text-xs font-medium text-nosql">
                <Leaf className="size-3.5" /> NoSQL
              </div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">{nosqlCount}</div>
            </div>
          </div>
          {sources.isPending ? (
            <div className="flex justify-center py-3 text-muted">
              <Spinner />
            </div>
          ) : sources.data && sources.data.length > 0 ? (
            <ul className="divide-y divide-border">
              {sources.data.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate font-medium">{s.name}</span>
                  <KindBadge kind={s.kind} />
                  <EngineBadge engine={s.engine} />
                  <StatusBadge status={s.status} message={s.status_message} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No databases attached yet.</p>
          )}
        </Card>
      </div>

      <div className="space-y-3">
        <QuickLink
          to={`${base}/schema`}
          icon={<Network className="size-4.5" />}
          title="Schema"
          description="ER diagram, conventions and DDL export."
        />
        <QuickLink
          to={`${base}/data`}
          icon={<Table2 className="size-4.5" />}
          title="Data"
          description="Browse and edit rows and documents."
        />
        <QuickLink
          to={`${base}/members`}
          icon={<Users className="size-4.5" />}
          title="Members"
          description="Invite collaborators and manage roles."
        />
        {can("admin") && (
          <QuickLink
            to={`${base}/api-keys`}
            icon={<KeyRound className="size-4.5" />}
            title="API keys"
            description="Keys for apps that talk to this project."
          />
        )}
      </div>
    </div>
  );
}
