import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { User } from "../../api/types";
import { AuthContext, type AuthStatus } from "../../auth/auth-context";
import { ToastContext } from "../../components/ui/toast-context";
import { InvitePage } from "./InvitePage";

const { api } = vi.hoisted(() => ({
  api: {
    invites: { preview: vi.fn(), accept: vi.fn() },
    auth: { providers: vi.fn(async () => ({ allow_signup: false })) },
  },
}));
vi.mock("../../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));
vi.mock("../../components/layout/AppLayout", () => ({
  AuthShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const user = { id: "u1", email: "friend@example.com" } as User;
const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };

async function render(status: AuthStatus) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const auth = {
    status,
    user: status === "authenticated" ? user : null,
    setUser: noop,
    refreshSession: async () => null,
    logout: async () => {},
  };
  await act(async () => {
    root.render(
      <QueryClientProvider client={qc}>
        <AuthContext.Provider value={auth}>
          <ToastContext.Provider value={toast}>
            <MemoryRouter initialEntries={["/invite/tok"]}>
              <Routes>
                <Route path="/invite/:token" element={<InvitePage />} />
                <Route path="/projects/:id" element={<p>project page</p>} />
              </Routes>
            </MemoryRouter>
          </ToastContext.Provider>
        </AuthContext.Provider>
      </QueryClientProvider>,
    );
  });
  // Let the preview query, the accept mutation and the navigation settle.
  for (let i = 0; i < 5; i++) await act(() => new Promise((r) => setTimeout(r, 0)));
  return el;
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.clearAllMocks();
});

describe("InvitePage after the invite was used", () => {
  it("sends a signed-in user who already accepted it (during sign-up) to the project", async () => {
    api.invites.preview.mockRejectedValue(new ApiError(404, "not_found", "Invite not found"));
    api.invites.accept.mockResolvedValue({ project_id: "p1" });
    const el = await render("authenticated");
    expect(api.invites.accept).toHaveBeenCalledWith("tok");
    expect(el.textContent).toContain("project page");
    expect(el.textContent).not.toContain("isn't valid");
  });

  it("still says the invite isn't valid when accept also fails", async () => {
    api.invites.preview.mockRejectedValue(new ApiError(404, "not_found", "Invite not found"));
    api.invites.accept.mockRejectedValue(new ApiError(404, "not_found", "Invite not found"));
    const el = await render("authenticated");
    expect(el.textContent).toContain("This invite isn't valid");
  });

  it("says the invite isn't valid to a signed-out visitor without calling accept", async () => {
    api.invites.preview.mockRejectedValue(new ApiError(404, "not_found", "Invite not found"));
    const el = await render("anonymous");
    expect(api.invites.accept).not.toHaveBeenCalled();
    expect(el.textContent).toContain("This invite isn't valid");
  });
});
