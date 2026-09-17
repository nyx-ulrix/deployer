import { Link } from "react-router-dom";
import { Database } from "lucide-react";
import { useDataSources } from "../../api/hooks";
import type { DataSource, Project } from "../../api/types";
import { PageSpinner } from "../../components/ui/Spinner";
import { EmptyState, ErrorState } from "../../components/ui/States";
import { useQueryConsoleMode } from "../../lib/consoleMode";
import { useProjectContext } from "../projects/project-context";
import { EditorConsole } from "./EditorConsole";
import { TerminalConsole } from "./TerminalConsole";
import { useQueryConsole } from "./useQueryConsole";

/** Project tab **Query** (QUERY_CONSOLE.md): SQL / MongoDB shell against one of the project's databases. */
export default function QueryTab() {
  const { project, can } = useProjectContext();
  const sources = useDataSources(project.id);

  if (sources.isPending) return <PageSpinner label="Loading databases…" />;
  if (sources.isError) return <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />;
  if (sources.data.length === 0) {
    return (
      <EmptyState
        icon={<Database className="size-5" />}
        title="No databases to query"
        description="Add a database on the Databases tab, then run SQL or MongoDB shell code against it here."
        action={
          <Link to={`/projects/${project.id}/databases`} className="text-sm font-medium text-accent hover:underline">
            Go to Databases
          </Link>
        }
      />
    );
  }
  return <QueryConsole key={project.id} project={project} sources={sources.data} readOnly={!can("developer")} />;
}

/** Holds the shared console state and renders the preferred layout; switching keeps input and history. */
function QueryConsole({ project, sources, readOnly }: { project: Project; sources: DataSource[]; readOnly: boolean }) {
  const console = useQueryConsole(project, sources, readOnly);
  const [mode] = useQueryConsoleMode();
  return mode === "terminal" ? <TerminalConsole console={console} /> : <EditorConsole console={console} />;
}
