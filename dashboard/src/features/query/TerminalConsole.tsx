import { useEffect, useRef, useState } from "react";
import { CornerDownLeft, Copy, Eraser, PanelRightOpen, Square } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { copyText } from "../../lib/clipboard";
import { ModeSwitch, PendingWriteAlert, ReadOnlyBadge, RowsSelect, TimeoutSelect } from "./ConsoleBits";
import { EntitySidebar } from "./EntitySidebar";
import { QueryEditor, type ConsoleAction } from "./QueryEditor";
import { SourceSelect } from "./SourceSelect";
import { transcriptText } from "./terminal";
import { Transcript } from "./Transcript";
import type { ConsoleApi } from "./useQueryConsole";

/** Shell-style layout: a dark panel with the transcript and the prompt pinned at the bottom. */
export function TerminalConsole({ console: c }: { console: ConsoleApi }) {
  const toast = useToast();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { entries } = c;

  // Keep the newest output in view, like a real terminal.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries]);

  const onAction = (action: ConsoleAction) => {
    switch (action) {
      case "submit":
        c.submitPrompt();
        break;
      case "history-prev":
        c.browseHistory(-1);
        break;
      case "history-next":
        c.browseHistory(1);
        break;
      case "clear":
        c.clearTranscript();
        break;
    }
  };

  const copyTranscript = async () => {
    const ok = await copyText(transcriptText(c.entries, c.prefs));
    if (ok) toast.success("Transcript copied.");
    else toast.error("Couldn't copy the transcript.");
  };

  const isSql = c.source.kind === "sql";

  return (
    <div className="flex flex-1 flex-col gap-3">
      {/* Header bar */}
      <div className="flex flex-wrap items-center gap-2">
        <SourceSelect
          sources={c.sources}
          value={c.source}
          onChange={c.selectSource}
          deviceName={c.deviceName}
          className="w-full sm:w-auto sm:min-w-64"
        />
        {c.readOnly && <ReadOnlyBadge />}
        <RowsSelect value={c.prefs.maxRows} onChange={(n) => c.setPrefs({ ...c.prefs, maxRows: n })} />
        <TimeoutSelect value={c.prefs.timeoutSeconds} onChange={(n) => c.setPrefs({ ...c.prefs, timeoutSeconds: n })} />
        <Button size="sm" icon={<Copy className="size-3.5" />} onClick={() => void copyTranscript()} disabled={c.entries.length === 0}>
          Copy transcript
        </Button>
        <Button size="sm" variant="ghost" icon={<Eraser className="size-3.5" />} onClick={c.clearTranscript} disabled={c.entries.length === 0}>
          Clear
        </Button>
        <div className="ml-auto flex items-center gap-1">
          <ModeSwitch />
          <Button
            size="icon"
            variant="ghost"
            aria-label={isSql ? "Show tables" : "Show collections"}
            title={isSql ? "Tables" : "Collections"}
            onClick={() => setDrawerOpen(true)}
          >
            <PanelRightOpen className="size-4" />
          </Button>
        </div>
      </div>

      {c.offline && <ErrorAlert error={c.schema.error} />}

      {/* The terminal panel is always dark: `dark` re-themes every token inside it. */}
      <div className="dark flex h-[calc(100dvh-19.5rem)] min-h-[22rem] flex-col overflow-hidden rounded-xl border border-border bg-bg text-fg shadow-xs">
        <div
          ref={scrollRef}
          role="log"
          aria-label="Transcript"
          aria-live="polite"
          className="min-h-0 flex-1 overflow-auto px-3 py-2 font-mono text-[13px] leading-5"
        >
          {c.entries.length === 0 ? (
            <p className="text-muted">Transcript cleared. Type \help for the commands.</p>
          ) : (
            <Transcript entries={c.entries} prefs={c.prefs} />
          )}
        </div>

        {c.pendingWrite && (
          <div className="border-t border-border px-2 py-2 font-sans">
            <PendingWriteAlert
              reason={c.pendingWrite.reason}
              onCancel={c.cancelPendingWrite}
              onConfirm={() => c.confirmPendingWrite({ clearInput: true })}
            />
          </div>
        )}

        {/* Prompt */}
        <div className="flex items-start gap-1 border-t border-border bg-surface px-2 py-1.5">
          <SourceSelect
            variant="prompt"
            sources={c.sources}
            value={c.source}
            onChange={c.selectSource}
            deviceName={c.deviceName}
            className="shrink-0 pt-px"
          />
          <QueryEditor
            key={c.source.id}
            onHandle={c.registerEditor}
            value={c.text}
            onChange={c.setText}
            kind={c.source.kind}
            engine={c.source.engine}
            entities={c.entities}
            mode="terminal"
            onAction={onAction}
            theme="dark"
            autoFocus
          />
          {c.running ? (
            <Button size="icon-sm" variant="ghost" aria-label="Cancel the running query" title="Cancel" onClick={c.cancel}>
              <Square className="size-3.5" />
            </Button>
          ) : (
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Run"
              title="Run (Enter)"
              onClick={c.submitPrompt}
              disabled={!c.text.trim()}
            >
              <CornerDownLeft className="size-3.5" />
            </Button>
          )}
        </div>
      </div>

      <Dialog
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        placement="right"
        size="sm"
        title={isSql ? "Tables" : "Collections"}
        description={`${c.source.name} — click one to insert a starter query at the prompt.`}
      >
        <EntitySidebar
          source={c.source}
          schema={c.schema}
          onInsert={(name) => {
            c.insertStarter(name);
            setDrawerOpen(false);
          }}
        />
      </Dialog>
    </div>
  );
}
