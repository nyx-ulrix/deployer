import { useEffect, useMemo, useRef } from "react";
import CodeMirror, {
  EditorView,
  ExternalChange,
  Facet,
  keymap,
  oneDarkHighlightStyle,
  Prec,
  type Extension,
  type ReactCodeMirrorRef,
} from "@uiw/react-codemirror";
import { acceptCompletion, type Completion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { javascript, javascriptLanguage } from "@codemirror/lang-javascript";
import { MySQL, PostgreSQL, sql, type SQLNamespace } from "@codemirror/lang-sql";
import { defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import type { DataSourceKind, Entity } from "../../api/types";
import { cn } from "../../lib/cn";
import { useTheme } from "../../lib/theme";
import { pickRunnable } from "./results";
import { shouldSubmitOnEnter } from "./terminal";

/** What a key binding asks the console to do (delivered through `onAction`). */
export type ConsoleAction = "submit" | "submit-next" | "history-prev" | "history-next" | "clear";
export type EditorMode = "editor" | "terminal";

export type QueryEditorHandle = {
  /** The selected text when there is one, else the whole document. */
  runnable: () => string;
  doc: () => string;
  /** Insert text at the cursor (on its own line) and focus the editor. */
  insert: (text: string) => void;
  /** Replace the whole document (cursor at the end) without firing `onChange`; the caller updates its own state. */
  setDoc: (text: string) => void;
  focus: () => void;
};

type Props = {
  value: string;
  onChange: (value: string) => void;
  kind: DataSourceKind;
  engine: string;
  /** Tables/collections of the selected source, for completion. */
  entities: readonly Entity[];
  /** `editor`: Ctrl/Cmd+Enter submits, Shift+Enter submits and moves on. `terminal`: shell-like Enter / history / Ctrl+L bindings. */
  mode: EditorMode;
  onAction: (action: ConsoleAction) => void;
  /** Force a colour scheme (the terminal panel is always dark). Defaults to the app theme. */
  theme?: "light" | "dark";
  autoFocus?: boolean;
  /** Editor mode only: grow with the content up to this CSS height instead of filling the parent. */
  maxHeight?: string;
  className?: string;
  /** Receives the imperative handle once mounted (and `null` on unmount). */
  onHandle?: (handle: QueryEditorHandle | null) => void;
};

// ---- Key bindings: they never touch React state; they raise a DOM event the component listens to. ----

const ACTION_EVENT = "deployer-console-action";
const kindFacet = Facet.define<DataSourceKind, DataSourceKind>({ combine: (values) => values[0] ?? "sql" });

function emit(view: EditorView, action: ConsoleAction): boolean {
  view.dom.dispatchEvent(new CustomEvent<ConsoleAction>(ACTION_EVENT, { bubbles: true, detail: action }));
  return true;
}

function insertNewline(view: EditorView): boolean {
  view.dispatch(view.state.replaceSelection("\n"), { scrollIntoView: true, userEvent: "input" });
  return true;
}

const cursorLine = (view: EditorView) => view.state.doc.lineAt(view.state.selection.main.head).number;
const tabAcceptsCompletion = { key: "Tab", run: acceptCompletion };

const editorKeys = Prec.high(
  keymap.of([
    { key: "Mod-Enter", run: (view) => emit(view, "submit") },
    { key: "Shift-Enter", run: (view) => emit(view, "submit-next") },
    tabAcceptsCompletion,
  ]),
);

const terminalKeys = Prec.high(
  keymap.of([
    { key: "Mod-Enter", run: (view) => emit(view, "submit") },
    {
      key: "Enter",
      run: (view) => (shouldSubmitOnEnter(view.state.facet(kindFacet), view.state.doc.toString()) ? emit(view, "submit") : false),
    },
    { key: "Shift-Enter", run: insertNewline },
    { key: "ArrowUp", run: (view) => (cursorLine(view) === 1 ? emit(view, "history-prev") : false) },
    { key: "ArrowDown", run: (view) => (cursorLine(view) === view.state.doc.lines ? emit(view, "history-next") : false) },
    { key: "Ctrl-l", run: (view) => emit(view, "clear") },
    tabAcceptsCompletion,
  ]),
);

// ---- Theme: colours come from the app's CSS tokens so the editor follows light/dark. ----

function editorTheme(dark: boolean, compact: boolean, fill: boolean): Extension {
  return [
    EditorView.theme(
      {
        "&": {
          backgroundColor: compact ? "transparent" : "var(--surface)",
          color: "var(--fg)",
          fontSize: "13px",
          height: fill ? "100%" : "auto",
        },
        "&.cm-focused": { outline: "none" },
        ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "1.6" },
        ".cm-content": { caretColor: "var(--accent)", padding: compact ? "4px 0" : "10px 0" },
        ".cm-line": { padding: compact ? "0 4px" : "0 12px" },
        ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--accent)" },
        "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
          { backgroundColor: dark ? "rgb(129 140 248 / 0.28)" : "rgb(79 70 229 / 0.16)" },
        ".cm-activeLine": { backgroundColor: dark ? "rgb(255 255 255 / 0.03)" : "rgb(17 24 39 / 0.03)" },
        ".cm-gutters": {
          backgroundColor: "var(--surface-2)",
          color: "var(--muted)",
          borderRight: "1px solid var(--border)",
        },
        ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--fg)" },
        ".cm-lineNumbers .cm-gutterElement": { padding: "0 8px 0 12px", minWidth: "2.75rem" },
        "&.cm-focused .cm-matchingBracket": { backgroundColor: "var(--accent-soft)", outline: "1px solid var(--accent)" },
        ".cm-selectionMatch": { backgroundColor: "var(--warning-soft)" },
        ".cm-placeholder": { color: "var(--muted)", opacity: "0.75", whiteSpace: "pre-wrap" },
        ".cm-tooltip": {
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          color: "var(--fg)",
          borderRadius: "10px",
          boxShadow: "0 10px 30px rgb(0 0 0 / 0.15)",
          overflow: "hidden",
        },
        ".cm-tooltip.cm-tooltip-autocomplete > ul": { fontFamily: "var(--font-mono)", fontSize: "12px" },
        ".cm-tooltip.cm-tooltip-autocomplete > ul > li": { padding: "3px 8px" },
        ".cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]": {
          backgroundColor: "var(--accent-soft)",
          color: "var(--fg)",
        },
        ".cm-completionDetail": { color: "var(--muted)", marginLeft: "0.75em", fontStyle: "normal" },
        ".cm-panels": { backgroundColor: "var(--surface-2)", color: "var(--fg)" },
        ".cm-panels.cm-panels-top": { borderBottom: "1px solid var(--border)" },
        ".cm-panels.cm-panels-bottom": { borderTop: "1px solid var(--border)" },
        ".cm-searchMatch": { backgroundColor: "var(--warning-soft)", outline: "1px solid var(--warning)" },
        ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: "var(--accent-soft)" },
      },
      { dark },
    ),
    syntaxHighlighting(dark ? oneDarkHighlightStyle : defaultHighlightStyle),
  ];
}

// ---- Completion ----

function sqlSchema(entities: readonly Entity[]): SQLNamespace {
  const ns: Record<string, string[]> = {};
  for (const e of entities) ns[e.name] = e.fields.map((f) => f.name);
  return ns;
}

const DB_METHODS = [
  "getCollection",
  "getCollectionNames",
  "getCollectionInfos",
  "getName",
  "stats",
  "version",
  "runCommand",
  "adminCommand",
  "createCollection",
  "dropDatabase",
];
const COLLECTION_METHODS = [
  "find",
  "findOne",
  "aggregate",
  "countDocuments",
  "estimatedDocumentCount",
  "distinct",
  "insertOne",
  "insertMany",
  "updateOne",
  "updateMany",
  "replaceOne",
  "deleteOne",
  "deleteMany",
  "bulkWrite",
  "findOneAndUpdate",
  "findOneAndDelete",
  "createIndex",
  "getIndexes",
  "dropIndex",
  "drop",
  "stats",
  "renameCollection",
];
const CURSOR_METHODS = [
  "limit",
  "skip",
  "sort",
  "project",
  "count",
  "toArray",
  "forEach",
  "map",
  "pretty",
  "explain",
  "batchSize",
  "hint",
  "next",
  "hasNext",
];

const isIdentifier = (s: string) => /^[A-Za-z_$][\w$]*$/.test(s);
const method = (label: string): Completion => ({ label, type: "method" });

/** Collection names after `db.` / inside `getCollection("…")`, plus the usual db/collection/cursor methods. */
function mongoCompletions(collections: readonly string[]) {
  const afterDb: Completion[] = [
    ...collections.map(
      (name): Completion => ({
        label: name,
        type: "variable",
        detail: "collection",
        boost: 3,
        apply: isIdentifier(name) ? name : `getCollection(${JSON.stringify(name)})`,
      }),
    ),
    ...DB_METHODS.map(method),
  ];
  const quoted: Completion[] = collections.map((name) => ({ label: name, type: "variable", detail: "collection" }));
  const collectionMethods = COLLECTION_METHODS.map(method);
  const cursorMethods = [...CURSOR_METHODS, ...COLLECTION_METHODS].map(method);
  const word = /^[\w$]*$/;

  return (ctx: CompletionContext): CompletionResult | null => {
    const inQuotes = ctx.matchBefore(/getCollection\(\s*["'][^"')]*/);
    if (inQuotes) {
      return { from: inQuotes.from + inQuotes.text.search(/["']/) + 1, options: quoted, validFor: /^[^"')]*$/ };
    }
    const onCollection = ctx.matchBefore(/\bdb\.(?:[\w$]+|getCollection\([^)]*\))\.[\w$]*/);
    if (onCollection) {
      return { from: onCollection.from + onCollection.text.lastIndexOf(".") + 1, options: collectionMethods, validFor: word };
    }
    const onCursor = ctx.matchBefore(/\)\s*\.[\w$]*/);
    if (onCursor) {
      return { from: onCursor.from + onCursor.text.lastIndexOf(".") + 1, options: cursorMethods, validFor: word };
    }
    const onDb = ctx.matchBefore(/\bdb\.[\w$]*/);
    if (onDb) return { from: onDb.from + 3, options: afterDb, validFor: word };
    return null;
  };
}

function placeholderFor(kind: DataSourceKind, engine: string, mode: EditorMode): string {
  if (kind === "nosql") {
    return mode === "terminal"
      ? "db.users.find().limit(20)"
      : 'db.users.find({ status: "active" }).limit(20)\n// MongoDB shell code — the value of the last expression is the result';
  }
  const table = engine === "postgresql" ? '"users"' : "`users`";
  return mode === "terminal"
    ? `SELECT * FROM ${table} LIMIT 100;`
    : `SELECT * FROM ${table} LIMIT 100;\n-- Several statements are fine, separated by ;`;
}

export function QueryEditor({ value, onChange, kind, engine, entities, mode, onAction, theme: forcedTheme, autoFocus, maxHeight, className, onHandle }: Props) {
  const { resolved } = useTheme();
  const dark = (forcedTheme ?? resolved) === "dark";
  const terminal = mode === "terminal";
  const fill = !terminal && !maxHeight;
  const cmRef = useRef<ReactCodeMirrorRef>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const handler = (e: Event) => onAction((e as CustomEvent<ConsoleAction>).detail);
    el.addEventListener(ACTION_EVENT, handler);
    return () => el.removeEventListener(ACTION_EVENT, handler);
  }, [onAction]);

  const language = useMemo<Extension>(() => {
    if (kind === "sql") {
      return sql({ dialect: engine === "postgresql" ? PostgreSQL : MySQL, schema: sqlSchema(entities), upperCaseKeywords: true });
    }
    return [javascript(), javascriptLanguage.data.of({ autocomplete: mongoCompletions(entities.map((e) => e.name)) })];
  }, [kind, engine, entities]);

  const theme = useMemo(() => editorTheme(dark, terminal, fill), [dark, terminal, fill]);
  const extensions = useMemo(
    () => [language, terminal ? terminalKeys : editorKeys, kindFacet.of(kind), theme, EditorView.lineWrapping],
    [language, terminal, kind, theme],
  );

  // The handle only talks to the CodeMirror view, so it is created once and handed to the owner.
  const handle = useMemo<QueryEditorHandle>(
    () => ({
      runnable: () => {
        const view = cmRef.current?.view;
        if (!view) return "";
        const { from, to } = view.state.selection.main;
        return pickRunnable(view.state.doc.toString(), from, to);
      },
      doc: () => cmRef.current?.view?.state.doc.toString() ?? "",
      insert: (text) => {
        const view = cmRef.current?.view;
        if (!view) return;
        const { from, to } = view.state.selection.main;
        const before = from > view.state.doc.lineAt(from).from ? "\n" : "";
        const after = to < view.state.doc.lineAt(to).to ? "\n" : "";
        const insert = `${before}${text}${after}`;
        view.dispatch({
          changes: { from, to, insert },
          selection: { anchor: from + before.length + text.length },
          scrollIntoView: true,
        });
        view.focus();
      },
      setDoc: (text) => {
        const view = cmRef.current?.view;
        if (!view) return;
        view.dispatch({
          changes: { from: 0, to: view.state.doc.length, insert: text },
          selection: { anchor: text.length },
          annotations: ExternalChange.of(true),
          scrollIntoView: true,
        });
      },
      focus: () => cmRef.current?.view?.focus(),
    }),
    [],
  );

  useEffect(() => {
    onHandle?.(handle);
    return () => onHandle?.(null);
  }, [handle, onHandle]);

  return (
    <div ref={wrapperRef} className={cn(terminal ? "min-w-0 flex-1" : fill && "h-full", className)}>
      <CodeMirror
        ref={cmRef}
        value={value}
        onChange={onChange}
        theme="none"
        extensions={extensions}
        placeholder={placeholderFor(kind, engine, mode)}
        basicSetup={
          terminal
            ? {
                lineNumbers: false,
                foldGutter: false,
                highlightActiveLine: false,
                highlightActiveLineGutter: false,
                crosshairCursor: false,
                tabSize: 2,
              }
            : { foldGutter: false, crosshairCursor: false, tabSize: 2 }
        }
        height={fill ? "100%" : "auto"}
        maxHeight={terminal ? "12rem" : maxHeight}
        autoFocus={autoFocus}
        className={fill ? "h-full" : undefined}
        aria-label={terminal ? "Query prompt" : "Query editor"}
      />
    </div>
  );
}
