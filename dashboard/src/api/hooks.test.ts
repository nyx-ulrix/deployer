import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { qk } from "./endpoints";
import { invalidateProjectSources } from "./hooks";

describe("invalidateProjectSources (A-181)", () => {
  it("refreshes this project and the projects list, not other projects", () => {
    const qc = new QueryClient();
    const keys = [qk.projects, qk.dataSources("p1"), qk.schema("p1"), qk.deletedSources("p1"), qk.project("p2"), qk.dataSources("p2")];
    for (const k of keys) qc.setQueryData(k, {});
    invalidateProjectSources(qc, "p1");
    const stale = keys.map((k) => qc.getQueryState(k)?.isInvalidated);
    expect(stale).toEqual([true, true, true, true, false, false]);
  });
});
