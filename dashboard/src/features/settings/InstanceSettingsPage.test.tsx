import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { ToastContext } from "../../components/ui/toast-context";
import { InstanceSettingsPage } from "./InstanceSettingsPage";

const provider = { client_id: null, secret_set: false, configured: false, callback_url: "" };
const { api } = vi.hoisted(() => ({
  api: {
    instance: {
      settings: vi.fn(),
      users: vi.fn(async () => []),
      projects: vi.fn(async () => []),
    },
  },
}));
vi.mock("../../api/endpoints", async (orig) => ({
  ...(await orig<object>()),
  api,
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const noop = () => {};

describe("open sign-up checkbox (A-091)", () => {
  it("warns that anyone who signs up can run code on this PC", async () => {
    api.instance.settings.mockResolvedValue({
      public_url: "http://localhost:8080",
      local_url: "http://localhost:8080",
      allow_signup: false,
      owner_only_projects: true,
      google: provider,
      github: provider,
      alert_webhook_url: null,
      api_key_rate_limit: 0,
    });
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => {
      createRoot(el).render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <ToastContext.Provider value={{ show: noop, success: noop, error: noop, info: noop }}>
            <MemoryRouter>
              <InstanceSettingsPage />
            </MemoryRouter>
          </ToastContext.Provider>
        </QueryClientProvider>,
      );
    });
    for (let i = 0; i < 5; i++) await act(() => new Promise((r) => setTimeout(r, 0)));
    const label = [...document.querySelectorAll("label")].find((l) => l.textContent?.includes("Allow anyone"));
    expect(label?.textContent).toContain("Anyone who signs up can create projects and run websites on this PC");
    expect(label?.textContent).toContain("use invite links");
  });
});
