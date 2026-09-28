import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { User } from "../../api/types";
import { AuthContext } from "../../auth/auth-context";
import { ToastContext } from "../../components/ui/toast-context";
import { ProjectsPage } from "./ProjectsPage";

const { api } = vi.hoisted(() => ({
  // create stays pending: the test only checks what was requested.
  api: {
    setup: { status: vi.fn() },
    projects: {
      list: vi.fn(async () => []),
      create: vi.fn(() => new Promise(() => {})),
    },
    devices: { list: vi.fn(async () => []) },
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
const settle = async () => {
  for (let i = 0; i < 5; i++)
    await act(() => new Promise((r) => setTimeout(r, 0)));
};

async function openNewProject(managed_mongodb: boolean) {
  api.setup.status.mockResolvedValue({ managed_mongodb });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const auth = {
    status: "authenticated" as const,
    user: { id: "u1" } as User,
    setUser: noop,
    refreshSession: async () => null,
    logout: async () => {},
  };
  await act(async () => {
    createRoot(el).render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <AuthContext.Provider value={auth}>
          <ToastContext.Provider
            value={{ show: noop, success: noop, error: noop, info: noop }}
          >
            <MemoryRouter>
              <ProjectsPage />
            </MemoryRouter>
          </ToastContext.Provider>
        </AuthContext.Provider>
      </QueryClientProvider>,
    );
  });
  await settle();
  const open = [...document.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("New project"),
  )!;
  await act(async () => open.click());
  await settle();
  const boxes = [
    ...document.querySelectorAll<HTMLInputElement>(
      "form#new-project input[type=checkbox]",
    ),
  ];
  return { sql: boxes[0], nosql: boxes[1] };
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.clearAllMocks();
});

describe("New project on a PC without AVX (A-017)", () => {
  it("unticks and disables MongoDB with a plain hint, and does not request it", async () => {
    const { sql, nosql } = await openNewProject(false);
    expect(sql.checked).toBe(true);
    expect(nosql.checked).toBe(false);
    expect(nosql.disabled).toBe(true);
    expect(document.body.textContent).toContain("can't run MongoDB");
    await act(async () =>
      document
        .querySelector("form#new-project")!
        .dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        ),
    );
    expect((api.projects.create.mock.calls as unknown[][])[0][0]).toMatchObject({
      provision: { sql: true, nosql: false },
    });
  });

  it("keeps MongoDB ticked when the CPU can run it", async () => {
    const { nosql } = await openNewProject(true);
    expect(nosql.checked).toBe(true);
    expect(nosql.disabled).toBe(false);
  });
});
