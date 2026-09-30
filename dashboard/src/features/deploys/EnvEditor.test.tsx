import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import type { EnvRow } from "./deploys";
import { EnvEditor } from "./EnvEditor";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function Harness() {
  const [rows, setRows] = useState<EnvRow[]>([
    { key: "A", value: "a" },
    { key: "B", value: "b" },
    { key: "C", value: "c" },
  ]);
  return <EnvEditor rows={rows} onChange={setRows} secret />;
}

const click = (el: Element) => act(() => (el as HTMLElement).click());
const types = () => [...document.querySelectorAll<HTMLInputElement>('input[aria-label$="value"]')].map((i) => `${i.value}:${i.type}`);

describe("EnvEditor", () => {
  it("keeps reveals on the same variables when a row is removed", async () => {
    document.body.innerHTML = "";
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => createRoot(el).render(<Harness />));

    const reveals = () => document.querySelectorAll('button[aria-label="Reveal value"], button[aria-label="Hide value"]');
    await click(reveals()[0]); // reveal A
    await click(reveals()[2]); // reveal C
    expect(types()).toEqual(["a:text", "b:password", "c:text"]);

    await click(document.querySelectorAll('button[aria-label="Remove variable"]')[0]); // remove A
    expect(types()).toEqual(["b:password", "c:text"]);
  });
});
