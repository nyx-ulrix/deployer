import type { DataSourceKind } from "../../api/types";

/** Shown in snippets until the key has been revealed in this session. */
export const KEY_PLACEHOLDER = "dpl_…";

export type SnippetLang = "curl" | "js" | "python";
export const SNIPPET_LANGS: { value: SnippetLang; label: string }[] = [
  { value: "curl", label: "curl" },
  { value: "js", label: "JavaScript" },
  { value: "python", label: "Python" },
];

export type SnippetInput = {
  /** Instance URL (`public_url`, else `window.location.origin`). Trailing slashes are fine. */
  baseUrl: string;
  projectId: string;
  /** Data source id; `{sid}` until the user picks one. */
  sourceId: string;
  kind: DataSourceKind;
  /** Table or collection name; a placeholder when the source has none yet. */
  entity: string;
  /** The revealed secret, or `null` for the placeholder. */
  key: string | null;
};

export type Snippet = { title: string; code: string };

/** `base` + `path` with exactly one slash between them. */
export function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

/** The request bodies the snippets send; kept as objects so the tests can prove they serialise to valid JSON. */
export function snippetBodies(kind: DataSourceKind) {
  return {
    insert: kind === "sql" ? { values: { name: "Ada" } } : { document: { name: "Ada" } },
    query: { query: kind === "sql" ? "SELECT 1" : "db.stats()" },
  };
}

type Req = { title: string; method: "GET" | "POST"; path: string; body?: object };

function requests(input: SnippetInput): Req[] {
  const { projectId, sourceId, kind, entity } = input;
  const source = `/v1/projects/${projectId}/data-sources/${sourceId}`;
  const items = kind === "sql" ? `${source}/tables/${entity}/rows` : `${source}/collections/${entity}/documents`;
  const noun = kind === "sql" ? "row" : "document";
  const bodies = snippetBodies(kind);
  return [
    { title: `List ${noun}s`, method: "GET", path: `${items}?limit=50` },
    { title: `Insert a ${noun}`, method: "POST", path: items, body: bodies.insert },
    { title: "Run a query", method: "POST", path: `${source}/query`, body: bodies.query },
  ];
}

export function buildSnippets(lang: SnippetLang, input: SnippetInput): Snippet[] {
  const key = input.key ?? KEY_PLACEHOLDER;
  return requests(input).map((r) => ({ title: r.title, code: render(lang, joinUrl(input.baseUrl, r.path), key, r) }));
}

function render(lang: SnippetLang, url: string, key: string, r: Req): string {
  const json = r.body ? JSON.stringify(r.body) : undefined;
  switch (lang) {
    case "curl":
      return [
        `curl ${r.method === "POST" ? "-X POST " : ""}'${url}' \\`,
        `  -H 'Authorization: Bearer ${key}'${json ? " \\" : ""}`,
        ...(json ? [`  -H 'Content-Type: application/json' \\`, `  -d '${json}'`] : []),
      ].join("\n");
    case "js":
      return [
        `const res = await fetch("${url}", {`,
        ...(r.method === "POST" ? [`  method: "POST",`] : []),
        `  headers: { Authorization: "Bearer ${key}"${json ? `, "Content-Type": "application/json"` : ""} },`,
        ...(json ? [`  body: JSON.stringify(${json}),`] : []),
        `});`,
        `const data = await res.json();`,
      ].join("\n");
    case "python":
      return [
        `import requests`,
        ``,
        `res = requests.${r.method.toLowerCase()}(`,
        `    "${url}",`,
        `    headers={"Authorization": "Bearer ${key}"},`,
        ...(json ? [`    json=${json},`] : []),
        `)`,
        `data = res.json()`,
      ].join("\n");
  }
}
