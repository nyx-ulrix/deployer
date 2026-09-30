import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SyncPage } from "./SyncPage";

const { setParams } = vi.hoisted(() => ({ setParams: vi.fn() }));
vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<object>()),
  useParams: () => ({ sourceId: "s1" }),
  useSearchParams: () => [new URLSearchParams(), setParams],
}));
vi.mock("../projects/project-context", () => ({
  useProjectContext: () => ({ project: { id: "p1" }, can: () => true }),
}));
vi.mock("../../api/hooks", () => ({
  useDataSourcesWithReplicas: () => ({ isPending: false, isError: false, data: [{ id: "s1", name: "db", replicas: [] }] }),
  useSyncConflicts: () => ({
    isPending: false,
    isError: false,
    data: [{ id: "c1", table: "t", key: { id: 1 }, op_primary: null, op_replica: null }],
  }),
}));
vi.mock("./hooks", () => ({ useMemberNames: () => () => "x" }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  document.body.innerHTML = "";
  setParams.mockClear();
});

describe("SyncPage conflict list", () => {
  it("opens a conflict with one history entry when its button is clicked", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => {
      createRoot(el).render(
        <MemoryRouter>
          <SyncPage />
        </MemoryRouter>,
      );
    });
    const button = [...el.querySelectorAll("button")].find((b) => b.textContent === "Resolve");
    await act(async () => button!.click());
    expect(setParams).toHaveBeenCalledTimes(1);
    expect(setParams).toHaveBeenCalledWith({ tab: "open", conflict: "c1" });

    await act(async () => el.querySelector("td")!.click());
    expect(setParams).toHaveBeenCalledTimes(2);
  });
});
