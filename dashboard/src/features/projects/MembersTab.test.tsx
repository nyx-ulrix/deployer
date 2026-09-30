import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Member, Role } from "../../api/types";
import { ToastContext } from "../../components/ui/toast-context";
import { hasRole } from "../../lib/roles";
import { MembersTab } from "./MembersTab";

const { api, ctx } = vi.hoisted(() => ({
  api: { members: { list: vi.fn() }, invites: { list: vi.fn() } },
  ctx: { myRole: "admin" as Role },
}));
vi.mock("../../api/endpoints", async (orig) => ({
  ...(await orig<object>()),
  api,
}));
vi.mock("../../auth/auth-context", () => ({
  useCurrentUser: () => ({ id: "me" }),
}));
vi.mock("./project-context", () => ({
  useProjectContext: () => ({
    project: { id: "p1", name: "Proj", my_role: ctx.myRole },
    can: (r: Role) => hasRole(ctx.myRole, r),
  }),
}));

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };
const member = (user_id: string, role: Role): Member => ({
  user_id,
  email: `${user_id}@example.test`,
  display_name: null,
  avatar_url: null,
  role,
  created_at: "2026-01-01T00:00:00Z",
});

async function render(myRole: Role) {
  ctx.myRole = myRole;
  api.members.list.mockResolvedValue([
    member("boss", "owner"),
    member("me", myRole),
    member("other-admin", "admin"),
    member("dev", "developer"),
  ]);
  api.invites.list.mockResolvedValue([]);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={qc}>
        <ToastContext.Provider value={toast}>
          <MemoryRouter>
            <MembersTab />
          </MemoryRouter>
        </ToastContext.Provider>
      </QueryClientProvider>,
    );
  });
  for (let i = 0; i < 5; i++)
    await act(() => new Promise((r) => setTimeout(r, 0)));
  return el;
}

const has = (el: HTMLElement, label: string) =>
  el.querySelector(`[aria-label="${label}"]`) !== null;

afterEach(() => {
  document.body.innerHTML = "";
});

describe("MembersTab", () => {
  it("an admin gets no role or remove controls for another admin (the API forbids it)", async () => {
    const el = await render("admin");
    expect(has(el, "Role for other-admin@example.test")).toBe(false);
    expect(has(el, "Remove other-admin@example.test")).toBe(false);
    expect(has(el, "Role for dev@example.test")).toBe(true);
    expect(has(el, "Remove dev@example.test")).toBe(true);
    expect(has(el, "Leave project")).toBe(true);
  });

  it("the owner can manage admins", async () => {
    const el = await render("owner");
    expect(has(el, "Role for other-admin@example.test")).toBe(true);
    expect(has(el, "Remove other-admin@example.test")).toBe(true);
  });
});
