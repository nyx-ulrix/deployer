import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { User } from "../../api/types";
import { AuthContext } from "../../auth/auth-context";
import { ToastContext } from "../../components/ui/toast-context";
import { SetupWizard } from "./SetupWizard";

const { api } = vi.hoisted(() => ({
  api: {
    setup: { status: vi.fn(async () => ({ initialized: true, managed_mongodb: true })) },
    instance: { settings: vi.fn(async () => ({ public_url: "http://localhost:8080" })) },
  },
}));
vi.mock("../../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));
vi.mock("../../components/layout/AppLayout", () => ({
  AuthShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};

describe("SetupWizard public URL step", () => {
  it("tells a first-time user to keep the prefilled address and points to remote access", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);
    const auth = {
      status: "authenticated" as const,
      user: { id: "u1", is_instance_owner: true } as User,
      setUser: noop,
      refreshSession: async () => null,
      logout: async () => {},
    };
    await act(async () => {
      root.render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <AuthContext.Provider value={auth}>
            <ToastContext.Provider value={{ show: noop, success: noop, error: noop, info: noop }}>
              <MemoryRouter>
                <SetupWizard />
              </MemoryRouter>
            </ToastContext.Provider>
          </AuthContext.Provider>
        </QueryClientProvider>,
      );
    });
    for (let i = 0; i < 5; i++) await act(() => new Promise((r) => setTimeout(r, 0)));

    const header = el.querySelector("h1")?.parentElement?.textContent ?? "";
    expect(header).toContain("Leave this as it is for now");
    expect(header).toContain("Domains & remote access");
    // Tailscale/Cloudflare detail lives only under Advanced, not in the main text.
    expect(header).not.toMatch(/Tailscale|Cloudflare|localhost/);
    expect(el.querySelector("details")?.textContent).toContain("Tailscale");
    act(() => root.unmount());
    el.remove();
  });
});
