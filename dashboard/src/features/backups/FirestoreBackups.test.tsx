import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DataSource, FirestoreBackups as Overview } from "../../api/types";
import { ToastContext } from "../../components/ui/toast-context";
import { FirestoreBackups } from "./FirestoreBackups";

const { api } = vi.hoisted(() => ({
  api: { cloud: { firestoreBackups: vi.fn(), firestoreSchedule: vi.fn(), firestoreRestore: vi.fn() } },
}));
vi.mock("../../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));
vi.mock("../projects/project-context", () => ({ useProjectContext: () => ({ project: { id: "p1" }, can: () => true }) }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };
const flush = async () => {
  for (let i = 0; i < 5; i++) await act(() => new Promise((r) => setTimeout(r, 0)));
};
const button = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("button")].filter((b) => b.textContent?.trim() === text).at(-1)!;
const tick = () => [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].at(-1)!;

const overview: Overview = {
  database: "(default)",
  location: "nam5",
  bucket: null,
  default_bucket: "deployer-demo-firestore",
  days: ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"],
  max_retention_days: { daily: 7, weekly: 98 },
  costs: { export: "EXPORT COST", import: "IMPORT COST", schedule: "SCHEDULE COST", restore: "RESTORE COST" },
  notes: { export: "Exports copy documents.", restore: "A restore makes a new database." },
  problems: { operations: "No permission to list operations." },
  schedules: [{ id: "s1", recurrence: "daily", day: null, retention_days: 7, created_at: null }],
  backups: [
    {
      name: "projects/demo/locations/nam5/backups/b1",
      id: "b1",
      location: "nam5",
      state: "READY",
      snapshot_time: "2026-09-30T00:00:00Z",
      expire_time: "2026-10-07T00:00:00Z",
      size_bytes: 2048,
      documents: 7,
    },
  ],
  operations: [],
};

afterEach(() => {
  document.body.innerHTML = "";
});

describe("Firestore backups (docs/CLOUD.md)", () => {
  it("lists schedules and backups and needs the cost tick to schedule or restore", async () => {
    api.cloud.firestoreBackups.mockResolvedValue(overview);
    api.cloud.firestoreSchedule.mockResolvedValue({ id: "s2" });
    api.cloud.firestoreRestore.mockResolvedValue({ data_source: { name: "Main restored" }, job: {} });
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => {
      createRoot(el).render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <ToastContext.Provider value={toast}>
            <FirestoreBackups source={{ id: "ds1", name: "Main", engine: "firestore" } as DataSource} />
          </ToastContext.Provider>
        </QueryClientProvider>,
      );
    });
    await flush();
    expect(el.textContent).toContain("Every day");
    expect(el.textContent).toContain("kept 7 days");
    expect(el.textContent).toContain("No permission to list operations.");

    await act(async () => button("Add schedule").click());
    expect(document.body.textContent).toContain("SCHEDULE COST");
    expect(button("Add schedule").disabled).toBe(true); // the dialog's button, until the tick
    await act(async () => tick().click());
    await act(async () => button("Add schedule").click());
    await flush();
    // A daily schedule exists, so the dialog offers the weekly one.
    expect(api.cloud.firestoreSchedule).toHaveBeenCalledWith("p1", "ds1", {
      recurrence: "weekly",
      day: "SUNDAY",
      retention_days: 7,
      confirm_billing: true,
    });

    await act(async () => button("Restore…").click());
    expect(document.body.textContent).toContain("RESTORE COST");
    expect(button("Restore").disabled).toBe(true);
    await act(async () => tick().click());
    await act(async () => button("Restore").click());
    await flush();
    expect(api.cloud.firestoreRestore).toHaveBeenCalledWith("p1", "ds1", {
      name: "Main restored",
      database: undefined,
      confirm_billing: true,
      backup: "projects/demo/locations/nam5/backups/b1",
    });
  });
});
