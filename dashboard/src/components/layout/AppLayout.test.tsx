import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { User } from "../../api/types";
import { AuthContext } from "../../auth/auth-context";
import { AppLayout } from "./AppLayout";

vi.mock("../../api/endpoints", async (orig) => ({
  ...(await orig<object>()),
  api: { monitoring: { summary: vi.fn(async () => ({ alerts: { visible: 0 } })) } },
}));
vi.mock("./ThemeToggle", () => ({ ThemeToggle: () => null }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

async function render(owner: boolean, path = "/") {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = { id: "u1", email: "me@example.com", is_instance_owner: owner } as User;
  const auth = { status: "authenticated" as const, user, setUser: noop, refreshSession: async () => null, logout: async () => {} };
  await act(async () => {
    root.render(
      <QueryClientProvider client={qc}>
        <AuthContext.Provider value={auth}>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route element={<AppLayout />}>
                <Route path="*" element={<Where />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>,
    );
  });
  return el;
}

const text = (els: Iterable<Element>) => [...els].map((e) => e.textContent);

describe("AppLayout", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("every account-menu item closes the menu and navigates to its page", async () => {
    const el = await render(true, "/somewhere");
    const menuTargets: Record<string, string> = {
      "Account settings": "/settings/account",
      Devices: "/settings/devices",
      "Export & import": "/settings/transfer",
      "Instance settings": "/settings/instance",
      Backups: "/settings/backups",
      "Domains & remote access": "/settings/remote-access",
      Monitoring: "/settings/monitoring",
      Projects: "/",
    };
    for (const [label, to] of Object.entries(menuTargets)) {
      await act(async () => el.querySelector<HTMLButtonElement>("[aria-haspopup=menu]")!.click());
      const item = [...el.querySelectorAll<HTMLButtonElement>("[role=menuitem]")].find((b) => b.textContent === label)!;
      await act(async () => item.click());
      expect(el.querySelector("[data-testid=where]")!.textContent).toBe(to);
      expect(el.querySelector("[role=menu]")).toBeNull();
    }
  });

  it("highlights Instance on every instance settings page and hides it from non-owners", async () => {
    const owner = await render(true, "/settings/backups");
    const nav = owner.querySelector("nav")!;
    expect(text(nav.querySelectorAll("a"))).toEqual(["Projects", "Devices", "Export & import", "Instance"]);
    const active = [...nav.querySelectorAll("a")].filter((a) => a.className.includes("bg-surface-2"));
    expect(text(active)).toEqual(["Instance"]);

    document.body.innerHTML = "";
    const member = await render(false);
    expect(text(member.querySelector("nav")!.querySelectorAll("a"))).toEqual(["Projects", "Devices", "Export & import"]);
  });
});
