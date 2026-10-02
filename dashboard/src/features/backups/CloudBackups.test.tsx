import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CloudBackupsInfo, DataSource, Role } from "../../api/types";
import { ToastContext } from "../../components/ui/toast-context";
import { hasRole } from "../../lib/roles";
import { CloudBackups } from "./CloudBackups";
import { restoredFrom } from "./cloudRestore";

const { api } = vi.hoisted(() => ({
  api: {
    cloud: { backups: vi.fn(), backup: vi.fn(), setPitr: vi.fn(), restore: vi.fn() },
    jobs: { get: vi.fn() },
  },
}));
vi.mock("../../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));
vi.mock("../projects/project-context", () => ({
  useProjectContext: () => ({
    project: { id: "p1", name: "Proj", my_role: "admin" },
    can: (r: Role) => hasRole("admin", r),
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
const lastCheckbox = () => [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].at(-1)!;

const source = { id: "s1", name: "Shop", engine: "dynamodb", cloud: { tables: ["orders", "users"] } } as unknown as DataSource;
const info: CloudBackupsInfo = {
  backups: [
    {
      table: "orders",
      arn: "arn:b1",
      name: "orders-20260901",
      status: "AVAILABLE",
      type: "USER",
      size_bytes: 10,
      created_at: "2026-09-01T00:00:00Z",
    },
  ],
  pitr: [
    { table: "orders", status: "ENABLED", earliest: "2026-09-01T00:00:00Z", latest: "2026-09-30T00:00:00Z", days: 35, problem: null },
    { table: "users", status: "DISABLED", earliest: null, latest: null, days: null, problem: null },
  ],
  cost: "backup cost",
  pitr_cost: "about US$0.20 per GB",
  restore: "Restoring never changes the original table",
  restore_cost: "about US$0.15 per GB restored",
};

async function render() {
  const el = document.createElement("div");
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ToastContext.Provider value={toast}>
          <CloudBackups source={source} />
        </ToastContext.Provider>
      </QueryClientProvider>,
    );
  });
  await flush();
  return el;
}

beforeEach(() => {
  api.cloud.backups.mockResolvedValue(info);
  api.jobs.get.mockResolvedValue({ id: "j1", status: "running", progress: 0.3, message: "AWS is copying the data" });
});
afterEach(() => {
  document.body.innerHTML = "";
  vi.clearAllMocks();
});

describe("DynamoDB point-in-time recovery and restores (docs/CLOUD.md C2-2)", () => {
  it("turns point-in-time recovery on only with the billing tick", async () => {
    api.cloud.setPitr.mockResolvedValue({ ...info.pitr[1], status: "ENABLED" });
    const el = await render();
    expect(el.textContent).toContain("Restorable from");
    await act(async () => button("Turn on").click());
    expect(document.body.textContent).toContain("about US$0.20 per GB");
    const confirm = [...document.querySelectorAll<HTMLButtonElement>("button")].filter((b) => b.textContent === "Turn on").at(-1)!;
    expect(confirm.disabled).toBe(true);
    await act(async () => lastCheckbox().click());
    await act(async () => confirm.click());
    await flush();
    expect(api.cloud.setPitr).toHaveBeenCalledWith("p1", "s1", { table: "users", enabled: true, confirm_billing: true });
  });

  it("restores a backup into a new database and follows the job", async () => {
    api.cloud.restore.mockResolvedValue({ data_source: { id: "s2", name: "orders restored" }, job: { id: "j1" } });
    await render();
    await act(async () => button("Restore").click());
    expect(document.body.textContent).toContain("The original table is not changed");
    expect(button("Restore into a new table").disabled).toBe(true);
    await act(async () => lastCheckbox().click());
    await act(async () => button("Restore into a new table").click());
    await flush();
    expect(api.cloud.restore).toHaveBeenCalledWith("p1", "s1", {
      name: "orders restored",
      backup_arn: "arn:b1",
      confirm_billing: true,
    });
    expect(document.body.textContent).toContain("Restoring in AWS");
  });

  it("restores a table to a picked time", async () => {
    api.cloud.restore.mockResolvedValue({ data_source: { id: "s3", name: "x" }, job: { id: "j1" } });
    await render();
    await act(async () => button("Restore to a time").click());
    const latest = [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].at(-2)!;
    await act(async () => latest.click()); // pick a time instead of the latest
    expect(document.querySelector('input[type="date"]')).not.toBeNull();
    await act(async () => lastCheckbox().click());
    await act(async () => button("Restore into a new table").click());
    await flush();
    const body = api.cloud.restore.mock.calls[0][2];
    expect(body.table).toBe("orders");
    expect(new Date(body.point_in_time).getTime()).toBe(new Date("2026-09-30T00:00:00Z").getTime());
  });

  it("says where a restored table came from", () => {
    expect(restoredFrom({ kind: "backup", table: "orders", backup: "orders-1", source_name: "Shop" })).toBe(
      "Restored from the backup orders-1 of orders (Shop)",
    );
    expect(restoredFrom({ kind: "point_in_time", table: "orders", latest: true })).toContain("when the restore started");
  });
});
