import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastContext } from "../../components/ui/toast-context";
import { ProjectSettingsTab } from "./ProjectSettingsTab";

const { api } = vi.hoisted(() => ({
  api: {
    dataSources: { list: vi.fn() },
    apps: { list: vi.fn() },
    projects: { remove: vi.fn() },
    transfers: { exportProjects: vi.fn() },
  },
}));
vi.mock("../../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));
vi.mock("./project-context", () => ({
  useProjectContext: () => ({
    project: { id: "p1", name: "Shop", slug: "shop", description: null, updated_at: "x" },
    can: () => true,
  }),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };
const flush = async () => {
  for (let i = 0; i < 5; i++) await act(() => new Promise((r) => setTimeout(r, 0)));
};
const button = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("button")].filter((b) => b.textContent?.trim() === text).at(-1)!;

afterEach(() => {
  document.body.innerHTML = "";
});

describe("Delete project with cloud resources (docs/CLOUD.md C2-5)", () => {
  it("lists what is in the cloud and needs a keep / delete choice before deleting", async () => {
    api.dataSources.list.mockResolvedValue([
      { id: "s1", name: "Shop DB", cloud: { created: true, resources: ["RDS instance deployer-shop-db"] } },
      { id: "s2", name: "Linked", cloud: { created: false, resources: [] } },
    ]);
    api.apps.list.mockResolvedValue([]);
    api.projects.remove.mockResolvedValue({ ok: true });
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => {
      createRoot(el).render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <ToastContext.Provider value={toast}>
            <MemoryRouter>
              <ProjectSettingsTab />
            </MemoryRouter>
          </ToastContext.Provider>
        </QueryClientProvider>,
      );
    });
    await flush();
    await act(async () => button("Delete project").click());
    await flush();
    expect(document.body.textContent).toContain("RDS instance deployer-shop-db");
    expect(document.body.textContent).not.toContain("Linked");

    const typed = document.querySelector<HTMLInputElement>('[aria-label="Type shop to confirm"]')!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(typed, "shop");
      typed.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(button("Delete project").disabled).toBe(true); // no choice yet

    const keep = [...document.querySelectorAll<HTMLInputElement>('input[name="project-cloud-choice"]')][1];
    await act(async () => keep.click());
    expect(button("Delete project").disabled).toBe(false);
    await act(async () => button("Delete project").click());
    await flush();
    expect(api.projects.remove).toHaveBeenCalledWith("p1", "shop", "keep");
  });
});
