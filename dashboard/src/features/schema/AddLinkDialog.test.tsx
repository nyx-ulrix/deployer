import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { ProjectSchema } from "../../api/types";
import { ToastContext } from "../../components/ui/toast-context";
import { AddLinkDialog } from "./AddLinkDialog";

vi.mock("../../api/endpoints", () => ({
  api: { schema: { createLink: vi.fn() } },
  qk: { schema: (p: string) => ["schema", p] },
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};
const toast = { show: noop, success: noop, error: noop, info: noop };
const schema = {
  sources: [
    {
      source_id: "s1",
      name: "shop",
      kind: "sql",
      engine: "mysql",
      status: "ok",
      error: null,
      relationships: [],
      entities: [{ name: "users", fields: [{ name: "id", data_type: "int", nullable: false, primary_key: true }] }],
    },
  ],
  links: [],
  conventions: [],
  generated_at: "",
} as unknown as ProjectSchema;

function pick(label: string, value: string) {
  const el = document.querySelector<HTMLSelectElement>(`[aria-label="${label}"]`)!;
  Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("change", { bubbles: true }));
}
const selfLink = "A field can't link to itself.";

describe("AddLinkDialog", () => {
  it("only says a field can't link to itself once both ends are chosen", async () => {
    document.body.innerHTML = "";
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => {
      createRoot(el).render(
        <QueryClientProvider client={new QueryClient()}>
          <ToastContext.Provider value={toast}>
            <AddLinkDialog projectId="p1" schema={schema} onClose={noop} />
          </ToastContext.Provider>
        </QueryClientProvider>,
      );
    });
    // Both ends on the same database with no table or field yet: unfinished, not an error.
    await act(async () => pick("From (referencing field) source", "s1"));
    expect(document.body.textContent).not.toContain(selfLink);

    await act(async () => pick("From (referencing field) entity", "users"));
    await act(async () => pick("To (referenced field) entity", "users"));
    expect(document.body.textContent).toContain(selfLink);
  });
});
