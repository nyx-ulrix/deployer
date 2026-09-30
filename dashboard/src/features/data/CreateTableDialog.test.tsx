import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { DataSource, Entity } from "../../api/types";
import { ToastContext } from "../../components/ui/toast-context";
import { api } from "../../api/endpoints";
import { CreateTableDialog } from "./CreateTableDialog";

vi.mock("../../api/endpoints", () => ({
  api: { schema: { createTable: vi.fn(async () => ({ name: "orders" })) } },
  qk: { schema: (p: string) => ["schema", p] },
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };
const customers = {
  name: "customers",
  fields: [{ name: "id", data_type: "bigint unsigned", nullable: false, primary_key: true }],
} as unknown as Entity;

function setValue(el: HTMLInputElement | HTMLSelectElement, value: string) {
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
}
const all = (label: string) => [...document.querySelectorAll<HTMLElement>(`[aria-label="${label}"]`)];

describe("CreateTableDialog", () => {
  it("speaks plain language, links with the right type and warns about cascade", async () => {
    document.body.innerHTML = "";
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => {
      createRoot(el).render(
        <QueryClientProvider client={new QueryClient()}>
          <ToastContext.Provider value={toast}>
            <CreateTableDialog
              projectId="p1"
              source={{ id: "s1", name: "shop", engine: "mysql" } as DataSource}
              entities={[customers]}
              onClose={noop}
              onCreated={noop}
            />
          </ToastContext.Provider>
        </QueryClientProvider>,
      );
    });
    const text = document.body.textContent ?? "";
    for (const jargon of ["Nullable", "Unique", "Auto-increment", "S1", "On delete"]) expect(text).not.toContain(jargon);
    expect(text).toContain("Can be empty");
    expect(text).toContain("No duplicates");
    // The id column shows a friendly kind, not a raw SQL box.
    expect((all("Kind of data")[0] as HTMLSelectElement).selectedOptions[0].textContent).toBe("ID number");
    expect(all("Column type")).toHaveLength(0);

    await act(async () => setValue(document.getElementById("create-table")!.querySelector("input")!, "orders"));
    await act(async () => [...document.querySelectorAll("button")].find((b) => b.textContent === "Add column")!.click());
    await act(async () => setValue(all("Column name")[1] as HTMLInputElement, "customer_id"));
    await act(async () => setValue(all("Links to table")[1] as HTMLSelectElement, "customers"));
    // Linking copies the linked column's type so MySQL accepts the foreign key.
    expect((all("Kind of data")[1] as HTMLSelectElement).value).toBe("BIGINT UNSIGNED");

    const onDelete = all("If a customers row is deleted")[0] as HTMLSelectElement;
    expect([...onDelete.options].map((o) => o.value)).toEqual(["", "set null", "cascade"]);
    expect(document.body.textContent).not.toContain("permanently delete");
    await act(async () => setValue(onDelete, "cascade"));
    expect(document.body.textContent).toContain("will also permanently delete every row of this table");

    await act(async () => (document.getElementById("create-table") as HTMLFormElement).requestSubmit());
    expect(api.schema.createTable).toHaveBeenCalledWith(
      "p1",
      "s1",
      expect.objectContaining({
        name: "orders",
        columns: [
          expect.objectContaining({ name: "id", type: "BIGINT UNSIGNED", primary_key: true }),
          expect.objectContaining({
            name: "customer_id",
            type: "BIGINT UNSIGNED",
            references: { table: "customers", column: "id", on_delete: "cascade" },
          }),
        ],
      }),
    );
  });
});
