import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { DataSource, Entity, JsonObject } from "../../api/types";
import { ToastContext } from "../../components/ui/toast-context";
import { api } from "../../api/endpoints";
import { RowDialog } from "./RowDialog";

vi.mock("../../api/endpoints", () => ({
  api: { rows: { insert: vi.fn(async () => ({ row: {} })), update: vi.fn(async () => ({ row: {} })) } },
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };
const entity = {
  name: "people",
  fields: [
    { name: "id", data_type: "int", nullable: false },
    { name: "name", data_type: "varchar(255)", nullable: true },
    { name: "bio", data_type: "varchar(255)", nullable: true },
    { name: "active", data_type: "tinyint(1)", nullable: false },
  ],
} as unknown as Entity;

async function render(row: JsonObject | null) {
  document.body.innerHTML = "";
  const el = document.createElement("div");
  document.body.appendChild(el);
  const qc = new QueryClient();
  await act(async () => {
    createRoot(el).render(
      <QueryClientProvider client={qc}>
        <ToastContext.Provider value={toast}>
          <RowDialog
            projectId="p1"
            source={{ id: "s1" } as DataSource}
            entity={entity}
            columns={["id", "name", "bio", "active"]}
            primaryKey={["id"]}
            row={row}
            onClose={noop}
            onSaved={noop}
          />
        </ToastContext.Provider>
      </QueryClientProvider>,
    );
  });
}

function type(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("RowDialog", () => {
  it("keeps the same focused control when a short value grows past 80 characters", async () => {
    await render({ id: 1, name: "Ann", bio: "x".repeat(120) });
    const before = document.getElementById("row-name") as HTMLInputElement;
    expect(before.tagName).toBe("INPUT");
    before.focus();
    await act(async () => type(before, "a".repeat(81)));
    const after = document.getElementById("row-name")!;
    expect(after).toBe(before);
    expect(document.activeElement).toBe(before);
    // A value that was already long opens as a textarea.
    expect(document.getElementById("row-bio")!.tagName).toBe("TEXTAREA");
  });

  it("edits a yes/no (TINYINT(1)) column with a checkbox and sends a boolean", async () => {
    await render({ id: 2, name: "Bo", bio: "", active: 0 });
    const box = document.getElementById("row-active") as HTMLInputElement;
    expect(box.type).toBe("checkbox");
    expect(box.checked).toBe(false);
    await act(async () => box.click());
    expect(box.checked).toBe(true);
    await act(async () => (document.getElementById("row-form") as HTMLFormElement).requestSubmit());
    expect(api.rows.update).toHaveBeenCalledWith("p1", "s1", "people", { id: 2 }, { active: true });
  });
});
