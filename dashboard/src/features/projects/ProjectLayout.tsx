import { Link, Outlet, useParams } from "react-router-dom";
import {
  ChevronLeft,
  Database,
  History,
  KeyRound,
  LayoutDashboard,
  Network,
  Settings,
  Table2,
  Users,
} from "lucide-react";
import { isApiError } from "../../api/client";
import { useProject } from "../../api/hooks";
import { Badge } from "../../components/ui/Badge";
import { PageSpinner } from "../../components/ui/Spinner";
import { ErrorState } from "../../components/ui/States";
import { NavTabs } from "../../components/ui/Tabs";
import { hasRole, ROLE_LABELS } from "../../lib/roles";
import { JobsButton } from "../jobs/JobsDrawer";
import type { ProjectOutletContext } from "./project-context";

export function ProjectLayout() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);

  if (project.isPending) return <PageSpinner />;
  if (project.isError) {
    const missing = isApiError(project.error) && (project.error.status === 404 || project.error.status === 403);
    return (
      <ErrorState
        title={missing ? "Project not found" : "Couldn't load project"}
        error={
          missing ? new Error("It may have been deleted, or you're not a member of it.") : project.error
        }
        onRetry={missing ? undefined : () => void project.refetch()}
      />
    );
  }

  const p = project.data;
  const base = `/projects/${p.id}`;
  const icon = "size-4";
  const tabs = [
    { to: base, label: "Overview", icon: <LayoutDashboard className={icon} />, end: true },
    { to: `${base}/databases`, label: "Databases", icon: <Database className={icon} /> },
    { to: `${base}/schema`, label: "Schema", icon: <Network className={icon} /> },
    { to: `${base}/data`, label: "Data", icon: <Table2 className={icon} /> },
    { to: `${base}/backups`, label: "Backups", icon: <History className={icon} /> },
    { to: `${base}/members`, label: "Members", icon: <Users className={icon} /> },
    ...(hasRole(p.my_role, "admin")
      ? [
          { to: `${base}/api-keys`, label: "API keys", icon: <KeyRound className={icon} /> },
          { to: `${base}/settings`, label: "Settings", icon: <Settings className={icon} /> },
        ]
      : []),
  ];
  const context: ProjectOutletContext = { project: p };

  return (
    <div className="flex flex-1 flex-col">
      <Link to="/" className="mb-2 inline-flex items-center gap-1 self-start text-sm text-muted hover:text-fg">
        <ChevronLeft className="size-4" /> Projects
      </Link>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h1 className="min-w-0 truncate text-xl font-semibold tracking-tight sm:text-2xl">{p.name}</h1>
        <Badge tone={p.my_role === "owner" ? "accent" : "neutral"}>{ROLE_LABELS[p.my_role]}</Badge>
        <div className="ml-auto">
          <JobsButton project={p} />
        </div>
      </div>
      <NavTabs items={tabs} className="mb-5" />
      <Outlet context={context} />
    </div>
  );
}
