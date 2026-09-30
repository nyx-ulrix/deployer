import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastContext } from "../../components/ui/toast-context";
import { MonitoringPage } from "./MonitoringPage";

const { api } = vi.hoisted(() => ({
  api: {
    monitoring: { metrics: vi.fn(), alerts: vi.fn() },
    instance: { settings: vi.fn() },
  },
}));
vi.mock("../../api/endpoints", async (orig) => ({
  ...(await orig<object>()),
  api,
}));

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };

async function render() {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={qc}>
        <ToastContext.Provider value={toast}>
          <MemoryRouter>
            <MonitoringPage />
          </MemoryRouter>
        </ToastContext.Provider>
      </QueryClientProvider>,
    );
  });
  for (let i = 0; i < 5; i++)
    await act(() => new Promise((r) => setTimeout(r, 0)));
  return el;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("MonitoringPage", () => {
  it("shows an error, not 'No active alerts', when alerts or settings fail to load", async () => {
    api.monitoring.metrics.mockRejectedValue(new Error("metrics down"));
    api.monitoring.alerts.mockRejectedValue(new Error("alerts down"));
    api.instance.settings.mockRejectedValue(new Error("settings down"));
    const el = await render();
    expect(el.textContent).not.toContain("No active alerts");
    expect(el.textContent).toContain("Couldn't load alerts");
    expect(el.textContent).toContain("alerts down");
    expect(el.textContent).toContain("Couldn't load alert settings");
    expect(el.textContent).toContain("settings down");
  });

  it("still says 'No active alerts' when the list is genuinely empty", async () => {
    api.monitoring.metrics.mockRejectedValue(new Error("metrics down"));
    api.monitoring.alerts.mockResolvedValue([]);
    api.instance.settings.mockRejectedValue(new Error("settings down"));
    const el = await render();
    expect(el.textContent).toContain("No active alerts");
  });
});
