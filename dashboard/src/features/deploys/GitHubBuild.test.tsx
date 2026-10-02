import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { App } from "../../api/types";
import { ToastContext } from "../../components/ui/toast-context";
import { BuildCard } from "./GitHubBuild";

const { api } = vi.hoisted(() => ({ api: { apps: { setBuild: vi.fn() }, jobs: { get: vi.fn() } } }));
vi.mock("../../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };
const flush = async () => {
  for (let i = 0; i < 5; i++) await act(() => new Promise((r) => setTimeout(r, 0)));
};
const button = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("button")].filter((b) => b.textContent?.trim() === text).at(-1)!;

const app = {
  id: "a1",
  name: "Shop",
  repo_url: "https://github.com/acme/shop",
  branch: "main",
  target: "aws_app",
  cloud: { provider: "aws", connection_name: "AWS", url: null, resources: [], secrets: null },
  build: { location: "pc" },
} as unknown as App;

afterEach(() => {
  document.body.innerHTML = "";
});

describe("Where it builds (docs/CLOUD.md C3)", () => {
  it("explains both choices and needs the GitHub billing tick before setting up", async () => {
    api.apps.setBuild.mockResolvedValue({ ...app, build: { location: "github", status: "setting_up" }, job_id: null });
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => {
      createRoot(el).render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <ToastContext.Provider value={toast}>
            <BuildCard projectId="p1" app={app} isAdmin />
          </ToastContext.Provider>
        </QueryClientProvider>,
      );
    });
    expect(el.textContent).toContain("Pushes still deploy when this PC is off");
    expect(el.textContent).toContain("2,000 a month");

    await act(async () => button("Build on GitHub Actions").click());
    await flush();
    expect(document.body.textContent).toContain("create an IAM role in your AWS account");
    expect(button("Set it up").disabled).toBe(true);
    const tick = [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].at(-1)!;
    await act(async () => tick.click());
    expect(button("Set it up").disabled).toBe(false);
    await act(async () => button("Set it up").click());
    await flush();
    expect(api.apps.setBuild).toHaveBeenCalledWith("p1", "a1", "github", true);
  });
});
