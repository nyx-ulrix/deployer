import { describe, expect, it } from "vitest";
import { buildSnippets, joinUrl, KEY_PLACEHOLDER, SNIPPET_LANGS, snippetBodies, type SnippetInput } from "./apiSnippets";

const input: SnippetInput = {
  baseUrl: "https://deployer.local/",
  projectId: "p1",
  sourceId: "s1",
  kind: "sql",
  entity: "users",
  key: null,
};

describe("joinUrl", () => {
  it("joins with exactly one slash", () => {
    expect(joinUrl("https://x.io", "/v1/a")).toBe("https://x.io/v1/a");
    expect(joinUrl("https://x.io/", "/v1/a")).toBe("https://x.io/v1/a");
    expect(joinUrl("https://x.io//", "v1/a")).toBe("https://x.io/v1/a");
  });
});

describe("buildSnippets", () => {
  it("uses the placeholder until the key is revealed, then the real key", () => {
    for (const { value } of SNIPPET_LANGS) {
      for (const s of buildSnippets(value, input)) {
        expect(s.code).toContain(`Bearer ${KEY_PLACEHOLDER}`);
        expect(s.code).not.toContain("//v1");
      }
      for (const s of buildSnippets(value, { ...input, key: "dpl_abc123" })) {
        expect(s.code).toContain("Bearer dpl_abc123");
        expect(s.code).not.toContain(KEY_PLACEHOLDER);
      }
    }
  });

  it("builds row endpoints for SQL and document endpoints for NoSQL", () => {
    const [sql] = buildSnippets("curl", input);
    expect(sql.code).toContain("https://deployer.local/v1/projects/p1/data-sources/s1/tables/users/rows?limit=50");
    const [nosql] = buildSnippets("curl", { ...input, kind: "nosql", entity: "orders" });
    expect(nosql.code).toContain("/data-sources/s1/collections/orders/documents?limit=50");
    expect(nosql.title).toBe("List documents");
  });

  it("embeds valid JSON bodies", () => {
    for (const kind of ["sql", "nosql"] as const) {
      const bodies = snippetBodies(kind);
      expect(JSON.parse(JSON.stringify(bodies.insert))).toEqual(bodies.insert);
      const curl = buildSnippets("curl", { ...input, kind });
      const bodyOf = (code: string) => JSON.parse(/-d '(.*)'$/.exec(code)?.[1] ?? "");
      expect(bodyOf(curl[1].code)).toEqual(bodies.insert);
      expect(bodyOf(curl[2].code)).toEqual(bodies.query);
    }
  });
});
