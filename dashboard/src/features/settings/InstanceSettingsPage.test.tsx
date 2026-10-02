import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { ToastContext } from "../../components/ui/toast-context";
import { InstanceSettingsPage } from "./InstanceSettingsPage";

const provider = {
  client_id: null,
  secret_set: false,
  configured: false,
  callback_url: "",
};
const { api } = vi.hoisted(() => ({
  api: {
    instance: {
      settings: vi.fn(),
      users: vi.fn(async (): Promise<unknown[]> => []),
      projects: vi.fn(async () => []),
      setUserActive: vi.fn(),
    },
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

const settings = {
  public_url: "http://localhost:8080",
  local_url: "http://localhost:8080",
  allow_signup: false,
  owner_only_projects: true,
  google: provider,
  github: provider,
  alert_webhook_url: null,
  api_key_rate_limit: 0,
};

async function renderPage() {
  const el = document.createElement("div");
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <ToastContext.Provider
          value={{ show: noop, success: noop, error: noop, info: noop }}
        >
          <MemoryRouter>
            <InstanceSettingsPage />
          </MemoryRouter>
        </ToastContext.Provider>
      </QueryClientProvider>,
    );
  });
  for (let i = 0; i < 5; i++)
    await act(() => new Promise((r) => setTimeout(r, 0)));
}

const button = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent === text)!;

describe("disabling an account (V-06)", () => {
  it("lists the API keys to rotate per project and says their admins revoke them", async () => {
    const user = {
      id: "u1",
      email: "admin@example.com",
      display_name: null,
      avatar_url: null,
      is_instance_owner: false,
      is_active: true,
      has_password: true,
      created_at: "2026-01-01T00:00:00Z",
      identities: [],
    };
    const key = {
      id: "k1",
      name: "Checkout",
      prefix: "dpl_service_abc",
      role: "service",
    };
    api.instance.settings.mockResolvedValue(settings);
    api.instance.users.mockResolvedValue([user]);
    api.instance.setUserActive.mockResolvedValue({
      ...user,
      is_active: false,
      api_keys_to_rotate: [
        { project_id: "p1", project_name: "Shop", keys: [key] },
      ],
    });
    document.body.innerHTML = "";
    await renderPage();
    await act(async () => button("Disable").click());
    await act(async () =>
      [...document.querySelectorAll("button")]
        .filter((b) => b.textContent === "Disable")
        .at(-1)!
        .click(),
    );
    for (let i = 0; i < 5; i++)
      await act(() => new Promise((r) => setTimeout(r, 0)));
    expect(api.instance.setUserActive).toHaveBeenCalledWith("u1", false);
    const text = document.body.textContent ?? "";
    expect(text).toContain("API keys to rotate");
    expect(text).toContain("Shop");
    expect(text).toContain("Checkout");
    expect(text).toContain("each project's admins to revoke them");
  });
});

describe("open sign-up checkbox (A-091)", () => {
  it("warns that anyone who signs up can run code on this PC", async () => {
    api.instance.settings.mockResolvedValue(settings);
    await renderPage();
    const label = [...document.querySelectorAll("label")].find((l) =>
      l.textContent?.includes("Allow anyone"),
    );
    expect(label?.textContent).toContain(
      "Anyone who signs up can create projects and run websites on this PC",
    );
    expect(label?.textContent).toContain("use invite links");
  });
});
