import { Eraser, PanelRightClose, PanelRightOpen, Play, Square, Terminal } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorAlert } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { engineLabel, formatTime } from "../../lib/format";
import { ModeSwitch, PendingWriteAlert, ReadOnlyBadge, RowsSelect, TimeoutSelect } from "./ConsoleBits";
import { MOD_KEY } from "./prefs";
import { EntitySidebar } from "./EntitySidebar";
import { HistoryMenu } from "./HistoryMenu";
import { MongoResults } from "./MongoResults";
import { QueryEditor, type ConsoleAction } from "./QueryEditor";
import { formatMs, mongoSummaryText, sqlSummaryText, summarizeSql } from "./results";
import { SourceSelect } from "./SourceSelect";
import { SqlResults } from "./SqlResults";
import { isDesktop, type ConsoleApi } from "./useQueryConsole";

/** Editor layout: toolbar, a resizable editor above a results panel, entity sidebar on the side. */
export function EditorConsole({ console: c }: { console: ConsoleApi }) {
  const { source, current, running } = c;
  const run = current?.run ?? null;
  const maxRows = run?.request.max_rows ?? c.prefs.maxRows;

  const onAction = (action: ConsoleAction) => {
    if (action === "submit") c.runEditor();
  };

  return (
    <div className="flex flex-1 flex-col gap-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <SourceSelect
          sources={c.sources}
          value={source}
          onChange={c.selectSource}
          deviceName={c.deviceName}
          className="w-full sm:w-auto sm:min-w-64"
        />
        <Button
          variant="primary"
          size="sm"
          icon={<Play className="size-3.5" />}
          onClick={c.runEditor}
          loading={running}
          disabled={!c.text.trim()}
          title={`Run the selection or everything (${MOD_KEY}+Enter)`}
        >
          Run
        </Button>
        {running && (
          <Button size="sm" variant="ghost" icon={<Square className="size-3.5" />} onClick={c.cancel}>
            Cancel
          </Button>
        )}
        <RowsSelect value={c.prefs.maxRows} onChange={(n) => c.setPrefs({ ...c.prefs, maxRows: n })} />
        <TimeoutSelect value={c.prefs.timeoutSeconds} onChange={(n) => c.setPrefs({ ...c.prefs, timeoutSeconds: n })} />
        <HistoryMenu entries={c.history} onPick={c.loadFromHistory} onClear={c.clearHistoryFor} />
        <Button size="sm" variant="ghost" icon={<Eraser className="size-3.5" />} onClick={c.clearResults} disabled={!run}>
          Clear results
        </Button>
        {c.readOnly && <ReadOnlyBadge />}
        <div className="ml-auto flex items-center gap-1">
          <ModeSwitch />
          <Button
            size="icon"
            variant="ghost"
            aria-label={c.sidebarOpen ? "Hide tables and collections" : "Show tables and collections"}
            title={c.sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            aria-pressed={c.sidebarOpen}
            onClick={() => c.setSidebarOpen((o) => !o)}
          >
            {c.sidebarOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          </Button>
        </div>
      </div>

      {c.offline && <ErrorAlert error={c.schema.error} />}

      <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
        {c.sidebarOpen && (
          <EntitySidebar
            source={source}
            schema={c.schema}
            onInsert={(name) => {
              c.insertStarter(name);
              if (!isDesktop()) c.setSidebarOpen(false);
            }}
            onClose={() => c.setSidebarOpen(false)}
            className="lg:order-last lg:w-64 lg:shrink-0"
          />
        )}

        <div className="flex min-w-0 flex-1 flex-col gap-3">
          {/* Editor */}
          <div
            className={cn(
              "flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-xs",
              "focus-within:border-accent focus-within:ring-3 focus-within:ring-ring",
            )}
          >
            <div className="h-52 resize-y overflow-hidden sm:h-64 lg:h-72">
              <QueryEditor
                key={source.id}
                onHandle={c.registerEditor}
                value={c.text}
                onChange={c.setText}
                kind={source.kind}
                engine={source.engine}
                entities={c.entities}
                mode="editor"
                onAction={onAction}
              />
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border px-3 py-1.5 text-[11px] text-muted">
              <span>
                {engineLabel(source.engine)} ·{" "}
                {source.kind === "sql"
                  ? "several statements allowed, separated by ;"
                  : "MongoDB shell — the value of the last expression is the result"}
              </span>
              <span className="ml-auto hidden sm:inline">
                Select part of the text to run only that ·{" "}
                <kbd className="rounded border border-border bg-surface-2 px-1 font-mono">{MOD_KEY}</kbd>+
                <kbd className="rounded border border-border bg-surface-2 px-1 font-mono">Enter</kbd> runs
              </span>
            </div>
          </div>

          {c.pendingWrite && (
            <PendingWriteAlert reason={c.pendingWrite.reason} onCancel={c.cancelPendingWrite} onConfirm={() => c.confirmPendingWrite()} />
          )}

          {/* Results */}
          <section className="flex min-w-0 flex-col gap-2" aria-live="polite" aria-label="Results">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
              <span className="text-sm font-semibold text-fg">Results</span>
              {current && run?.status === "done" && (
                <>
                  <Badge tone={run.response.kind === "sql" ? "sql" : "nosql"}>{engineLabel(run.response.engine)}</Badge>
                  <span>{run.response.kind === "sql" ? sqlSummaryText(summarizeSql(run.response)) : mongoSummaryText(run.response)}</span>
                  <span>· {formatMs(run.response.duration_ms)}</span>
                  <span>· {formatTime(current.at)}</span>
                </>
              )}
              {current && run?.status === "failed" && <span>{formatTime(current.at)}</span>}
              {run?.status === "running" && <span>up to {run.request.timeout_seconds} s</span>}
            </div>

            {!run && (
              <EmptyState
                icon={<Terminal className="size-5" />}
                title="Run a query"
                description={
                  source.kind === "sql"
                    ? `Results appear here, one card per statement. Press ${MOD_KEY}+Enter or click Run.`
                    : `The shell's output and the value of the last expression appear here. Press ${MOD_KEY}+Enter or click Run.`
                }
              />
            )}
            {run?.status === "running" && (
              <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-6 text-sm text-muted">
                <Spinner className="size-4" />
                Running against {source.name}…
                <Button size="sm" variant="ghost" className="ml-auto" onClick={c.cancel}>
                  Cancel
                </Button>
              </div>
            )}
            {run?.status === "failed" &&
              (run.failure.offline ? (
                <ErrorAlert error={run.error} />
              ) : (
                <Alert tone={run.failure.code === "read_only_role" ? "warning" : "danger"} title={run.failure.title}>
                  {run.failure.message}
                </Alert>
              ))}
            {current &&
              run?.status === "done" &&
              (run.response.kind === "sql" ? (
                <SqlResults key={current.id} response={run.response} maxRows={maxRows} />
              ) : (
                <MongoResults key={current.id} response={run.response} maxRows={maxRows} />
              ))}
          </section>
        </div>
      </div>
    </div>
  );
}
