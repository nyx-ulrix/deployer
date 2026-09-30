import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { App } from "../../api/types";
import { DeploysTab } from "./DeploysTab";
import { PRESETS } from "./deploys";

const { api } = vi.hoisted(() => ({ api: { apps: { list: vi.fn() } } }));
vi.mock("../../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));
vi.mock("../projects/project-context", () => ({
  useProjectContext: () => ({ project: { id: "p1", name: "Proj", my_role: "admin" }, can: () => true }),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("DeploysTab app list", () => {
  it("keeps the site link out of the row link (A-179)", async () => {
    api.apps.list.mockResolvedValue([
      {
        id: "a1",
        name: "shop",
        preset: Object.keys(PRESETS)[0],
        target: "local",
        branch: "main",
        live_deployment: null,
        urls: ["https://shop.example.test"],
        local_url: null,
      } as unknown as App,
    ]);
    const el = document.createElement("div");
    document.body.appendChild(el);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    await act(async () => {
      createRoot(el).render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <DeploysTab />
          </MemoryRouter>
        </QueryClientProvider>,
      );
    });
    for (let i = 0; i < 5; i++) await act(() => new Promise((r) => setTimeout(r, 0)));

    const links = el.querySelectorAll("li a");
    expect(links).toHaveLength(2);
    expect(el.querySelector("a a")).toBeNull();
    expect(links[0].getAttribute("href")).toBe("/projects/p1/deploys/a1");
    expect(links[1].getAttribute("href")).toBe("https://shop.example.test");
  });
});
