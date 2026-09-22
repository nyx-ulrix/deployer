import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import { Button } from "../../components/ui/Button";
import { Checkbox, Select } from "../../components/ui/Input";
import { ErrorAlert } from "../../components/ui/States";

const TAILS = [100, 200, 500];

/** `GET /apps/{id}/logs?tail=` — the live container's recent stdout/stderr. */
export function RuntimeLogs({ projectId, appId }: { projectId: string; appId: string }) {
  const [tail, setTail] = useState(200);
  const [auto, setAuto] = useState(false);
  const logs = useQuery({
    queryKey: [...qk.appLogs(projectId, appId), tail],
    queryFn: () => api.apps.logs(projectId, appId, tail),
    refetchInterval: auto ? 5000 : false,
  });

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={tail} onChange={(e) => setTail(Number(e.target.value))} className="h-8 w-auto text-xs sm:text-xs" aria-label="Lines">
          {TAILS.map((n) => (
            <option key={n} value={n}>
              Last {n} lines
            </option>
          ))}
        </Select>
        <Button size="sm" icon={<RefreshCw className="size-3.5" />} loading={logs.isFetching} onClick={() => void logs.refetch()}>
          Refresh
        </Button>
        <Checkbox label="Auto-refresh every 5 s" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="ml-auto" />
      </div>
      {logs.isError ? (
        <ErrorAlert error={logs.error} />
      ) : (
        <pre className="max-h-96 min-h-24 overflow-auto rounded-xl border border-border bg-surface-2 p-3 font-mono text-xs leading-5 whitespace-pre-wrap break-words" aria-label="Runtime logs">
          {logs.data
            ? logs.data.lines.length > 0
              ? logs.data.lines.join("\n")
              : <span className="text-muted">{logs.data.container ? "No output yet." : "No live container — deploy the app first."}</span>
            : <span className="text-muted">Loading…</span>}
        </pre>
      )}
      {logs.data?.container && <p className="text-xs text-muted">Container <code className="font-mono">{logs.data.container}</code></p>}
    </div>
  );
}
