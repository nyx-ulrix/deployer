import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { qk } from "../../api/endpoints";
import type { CliInput } from "../../api/types";
import { InputRequestPage } from "./InputRequestPage";

const { api, auth } = vi.hoisted(() => ({
  api: { inputs: { get: vi.fn(), submit: vi.fn() } },
  auth: { user: { email: "member@example.com" }, logout: vi.fn() },
}));
vi.mock("../../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));
vi.mock("../../auth/auth-context", () => ({ useAuth: () => auth }));
vi.mock("../../components/layout/AppLayout", () => ({
  AuthShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const NOTICE = "Deployer never asks for your account password or a sign-in approval code on this page.";
const future = () => new Date(Date.now() + 20 * 60_000).toISOString();

function request(over: Partial<CliInput> = {}): CliInput {
  return {
    id: "req1",
    title: "Google sign-in for Kanban",
    description: "Paste the client id and secret.\n\nRedirect URI: https://kanban.example.com/auth/callback",
    fields: [
      {
        key: "GOOGLE_CLIENT_ID",
        label: "Client ID",
        pattern: "^[0-9]+-[a-z0-9]+\\.apps\\.googleusercontent\\.com$",
        help: "Ends in .apps.googleusercontent.com",
        link: "https://console.cloud.google.com/apis/credentials",
        link_label: "Google Cloud console",
      },
      { key: "GOOGLE_CLIENT_SECRET", label: "Client secret", secret: true },
      { key: "NOTES", label: "Notes", multiline: true, optional: true },
    ],
    apps: [{ id: "a1", name: "Kanban", project_name: "Home" }],
    unavailable_apps: 0,
    requested_by: { kind: "cli", name: "jiaen-server (agent)", prefix: "dpt_ab12cd34" },
    status: "pending",
    expires_at: future(),
    created_at: new Date().toISOString(),
    ...over,
  };
}

const settle = async () => {
  for (let i = 0; i < 5; i++) await act(() => new Promise((r) => setTimeout(r, 0)));
};

function LoginProbe() {
  const location = useLocation();
  return <p id="login-probe">{location.pathname + location.search}</p>;
}

async function render() {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/input/req1"]}>
          <Routes>
            <Route path="/input/:id" element={<InputRequestPage />} />
            <Route path="/login" element={<LoginProbe />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
  await settle();
  return Object.assign(el, { qc });
}

function type(el: HTMLElement, selector: string, value: string) {
  const input = el.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector)!;
  const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function submitForm(el: HTMLElement) {
  await act(async () => {
    el.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();
  });
  await settle();
}

// jsdom drops -webkit-text-security from the style attribute; React still sets it on the style object.
const masked = (input: HTMLElement) =>
  (input.style as unknown as Record<string, string | undefined>).WebkitTextSecurity === "disc";

const ID = "123-abc.apps.googleusercontent.com";

afterEach(() => {
  document.body.innerHTML = "";
  vi.clearAllMocks();
});

describe("InputRequestPage", () => {
  it("renders each field type, the link, who asked, the notice and where the values go", async () => {
    api.inputs.get.mockResolvedValue(request());
    const el = await render();
    expect(api.inputs.get).toHaveBeenCalledWith("req1");
    expect(el.querySelector("h1")?.textContent).toBe("Google sign-in for Kanban");
    expect(el.textContent).toContain("Redirect URI: https://kanban.example.com/auth/callback");
    expect(el.querySelector("textarea#input-NOTES")).not.toBeNull();
    const link = el.querySelector<HTMLAnchorElement>('a[target="_blank"]')!;
    expect(link.textContent).toContain("Open Google Cloud console");
    expect(link.rel).toBe("noopener noreferrer");
    expect(link.title).toBe("Open Google Cloud console (console.cloud.google.com)");
    expect(link.querySelector("span.truncate")?.textContent).toBe("Open Google Cloud console");
    expect(el.textContent).toContain("Ends in .apps.googleusercontent.com");
    expect(el.textContent).toContain("Will be saved to the Environment of Home / Kanban.");
    expect(el.textContent).toContain("Asked by command line 'jiaen-server (agent)' (dpt_ab12cd34…)");
    expect(el.textContent).toContain(NOTICE);
  });

  it("never renders a password field or anything a browser takes for a sign-in form", async () => {
    api.inputs.get.mockResolvedValue(request());
    const el = await render();
    expect(el.querySelector('input[type="password"]')).toBeNull();
    const form = el.querySelector("form")!;
    expect(form.getAttribute("autocomplete")).toBe("off");
    expect(form.getAttribute("data-form-type")).toBe("other");
    for (const c of el.querySelectorAll<HTMLElement>("form input, form textarea")) {
      expect(c.getAttribute("autocomplete")).toBe("off");
      expect(c.getAttribute("spellcheck")).toBe("false");
      expect(c.hasAttribute("data-1p-ignore")).toBe(true);
      expect(c.getAttribute("data-lpignore")).toBe("true");
      expect(c.hasAttribute("data-bwignore")).toBe(true);
      expect(c.getAttribute("data-form-type")).toBe("other");
    }
    const secret = el.querySelector<HTMLInputElement>("#input-GOOGLE_CLIENT_SECRET")!;
    expect(secret.type).toBe("text");
    expect(masked(secret)).toBe(true);
    expect(masked(el.querySelector("#input-GOOGLE_CLIENT_ID")!)).toBe(false);
  });

  it("keeps the show toggle's name constant and reports its state with aria-pressed", async () => {
    api.inputs.get.mockResolvedValue(request());
    const el = await render();
    const secret = el.querySelector<HTMLInputElement>("#input-GOOGLE_CLIENT_SECRET")!;
    const toggle = el.querySelector<HTMLButtonElement>('button[aria-label="Show Client secret"]')!;
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    act(() => toggle.click());
    expect(toggle.getAttribute("aria-label")).toBe("Show Client secret");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    expect(masked(secret)).toBe(false);
    act(() => toggle.click());
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(masked(secret)).toBe(true);
  });

  it("says when a dashboard session asked", async () => {
    api.inputs.get.mockResolvedValue(request({ requested_by: { kind: "session", name: null, prefix: null } }));
    const el = await render();
    expect(el.textContent).toContain("Asked from a dashboard session");
    expect(el.textContent).not.toContain("Asked by command line");
  });

  it("names the project of every app, so same-named apps are told apart", async () => {
    api.inputs.get.mockResolvedValue(
      request({
        apps: [
          { id: "a1", name: "Kanban", project_name: "Production" },
          { id: "a2", name: "Kanban", project_name: "Staging" },
        ],
      }),
    );
    const el = await render();
    expect(el.textContent).toContain("Will be saved to the Environment of Production / Kanban and Staging / Kanban.");
  });

  it("checks required fields and patterns before sending", async () => {
    api.inputs.get.mockResolvedValue(request());
    const el = await render();
    await submitForm(el);
    expect(el.textContent).toContain("Enter Client ID.");
    expect(el.textContent).toContain("Enter Client secret.");
    type(el, "#input-GOOGLE_CLIENT_ID", "not-an-id");
    type(el, "#input-GOOGLE_CLIENT_SECRET", "s3cret");
    await submitForm(el);
    expect(el.textContent).toContain("Client ID doesn't look right");
    expect(api.inputs.submit).not.toHaveBeenCalled();
  });

  it("checks patterns with the u flag and skips ones JS can't compile", async () => {
    api.inputs.get.mockResolvedValue(
      request({
        fields: [
          // Python-only syntax: throws with the u flag (without it \A and \Z would be the letters A and Z).
          { key: "CODE", label: "Code", pattern: "\\A[0-9]{6}\\Z" },
          { key: "MAX", label: "Max", pattern: "[0-9]{,6}" },
          // With the u flag `.` counts code points, so three emoji are three characters.
          { key: "EMOJI", label: "Emoji", pattern: ".{1,3}" },
        ],
      }),
    );
    api.inputs.submit.mockResolvedValue({ ok: true, keys: ["CODE", "MAX", "EMOJI"] });
    const el = await render();
    type(el, "#input-CODE", "123456");
    type(el, "#input-MAX", "123");
    type(el, "#input-EMOJI", "😀😀😀");
    await submitForm(el);
    expect(api.inputs.submit).toHaveBeenCalledWith("req1", { CODE: "123456", MAX: "123", EMOJI: "😀😀😀" });
  });

  it("submits trimmed values, clears them, shows the saved state and marks the cached request submitted", async () => {
    api.inputs.get.mockResolvedValue(request());
    api.inputs.submit.mockResolvedValue({ ok: true, keys: ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"] });
    const el = await render();
    type(el, "#input-GOOGLE_CLIENT_ID", `  ${ID} `);
    type(el, "#input-GOOGLE_CLIENT_SECRET", "s3cret");
    await submitForm(el);
    expect(api.inputs.submit).toHaveBeenCalledWith("req1", { GOOGLE_CLIENT_ID: ID, GOOGLE_CLIENT_SECRET: "s3cret" });
    expect(el.textContent).toContain("Saved. You can close this tab; the terminal continues by itself.");
    expect(el.textContent).toContain("Saved to the Environment of Home / Kanban");
    expect(el.querySelector("input")).toBeNull();
    expect(el.innerHTML).not.toContain("s3cret");
    // Back to this page later: the cache says submitted, so the form doesn't come back.
    expect(el.qc.getQueryData<CliInput>(qk.input("req1"))?.status).toBe("submitted");
  });

  it("says the values go to the command line when no app is named", async () => {
    api.inputs.get.mockResolvedValue(request({ apps: [] }));
    api.inputs.submit.mockResolvedValue({ ok: true, keys: ["GOOGLE_CLIENT_ID"] });
    const el = await render();
    type(el, "#input-GOOGLE_CLIENT_ID", ID);
    type(el, "#input-GOOGLE_CLIENT_SECRET", "x");
    await submitForm(el);
    expect(el.textContent).toContain("Sent to the command line that asked for it");
  });

  it("handles field keys named like Object.prototype members", async () => {
    api.inputs.get.mockResolvedValue(
      request({
        apps: [],
        fields: [
          { key: "__proto__", label: "Proto" },
          { key: "constructor", label: "Constructor" },
          { key: "toString", label: "To string" },
        ],
      }),
    );
    api.inputs.submit.mockResolvedValue({ ok: true, keys: ["__proto__", "constructor", "toString"] });
    const el = await render();
    for (const k of ["__proto__", "constructor", "toString"]) {
      const c = el.querySelector(`#input-${k}`)!;
      expect(c.getAttribute("aria-invalid")).toBeNull();
      expect((c as HTMLInputElement).value).toBe("");
    }
    await submitForm(el);
    expect(el.textContent).toContain("Enter Proto.");
    expect(el.textContent).toContain("Enter Constructor.");
    type(el, "#input-__proto__", "p");
    type(el, "#input-constructor", "c");
    type(el, "#input-toString", "t");
    await submitForm(el);
    const sent = api.inputs.submit.mock.calls[0][1] as Record<string, string>;
    expect(JSON.stringify(sent)).toBe('{"__proto__":"p","constructor":"c","toString":"t"}');
    expect(el.textContent).toContain("Saved. You can close this tab");
  });

  it("shows a 422 next to the field it names, and drops it when the field is edited", async () => {
    api.inputs.get.mockResolvedValue(request());
    api.inputs.submit.mockRejectedValue(
      new ApiError(422, "validation_error", "Value is too long", { field: "GOOGLE_CLIENT_SECRET" }),
    );
    const el = await render();
    type(el, "#input-GOOGLE_CLIENT_ID", ID);
    type(el, "#input-GOOGLE_CLIENT_SECRET", "x");
    await submitForm(el);
    const err = el.querySelector("#input-GOOGLE_CLIENT_SECRET-error");
    expect(err?.textContent).toBe("Value is too long");
    expect(el.textContent?.match(/Value is too long/g)).toHaveLength(1);
    type(el, "#input-GOOGLE_CLIENT_SECRET", "xy");
    expect(el.querySelector("#input-GOOGLE_CLIENT_SECRET-error")).toBeNull();
    expect(el.textContent).not.toContain("Value is too long");
  });

  it("clears a previous server error once a field is edited", async () => {
    api.inputs.get.mockResolvedValue(request());
    api.inputs.submit.mockRejectedValueOnce(new ApiError(500, "internal", "Something broke"));
    const el = await render();
    type(el, "#input-GOOGLE_CLIENT_ID", ID);
    type(el, "#input-GOOGLE_CLIENT_SECRET", "x");
    await submitForm(el);
    expect(el.textContent).toContain("Something broke");
    type(el, "#input-GOOGLE_CLIENT_SECRET", "");
    expect(el.textContent).not.toContain("Something broke");
    await submitForm(el);
    expect(el.textContent).toContain("Enter Client secret.");
    expect(el.textContent).not.toContain("Something broke");
  });

  it("refetches after a 409 and ends on the request's real state", async () => {
    api.inputs.get.mockResolvedValueOnce(request()).mockResolvedValueOnce(request({ status: "submitted" }));
    api.inputs.submit.mockRejectedValue(new ApiError(409, "input_not_pending", "This request is no longer open"));
    const el = await render();
    type(el, "#input-GOOGLE_CLIENT_ID", ID);
    type(el, "#input-GOOGLE_CLIENT_SECRET", "x");
    await submitForm(el);
    expect(api.inputs.get).toHaveBeenCalledTimes(2);
    expect(el.textContent).toContain("Already filled in");
    expect(el.querySelector("form")).toBeNull();
  });

  it("shows why it can't be filled when the 409 says an app is unavailable", async () => {
    api.inputs.get.mockResolvedValueOnce(request()).mockResolvedValueOnce(request({ unavailable_apps: 1 }));
    api.inputs.submit.mockRejectedValue(
      new ApiError(409, "input_apps_unavailable", "An app of this request is no longer available"),
    );
    const el = await render();
    type(el, "#input-GOOGLE_CLIENT_ID", ID);
    type(el, "#input-GOOGLE_CLIENT_SECRET", "x");
    await submitForm(el);
    expect(el.textContent).toContain("This request can't be filled in");
    expect(el.querySelector("form")).toBeNull();
  });

  it("shows a non-fillable message instead of the form when apps are unavailable", async () => {
    api.inputs.get.mockResolvedValue(request({ unavailable_apps: 2 }));
    const el = await render();
    expect(el.querySelector("form")).toBeNull();
    expect(el.textContent).toContain("This request can't be filled in");
    expect(el.textContent).toContain("2 of the apps it would save to no longer exist");
    expect(el.textContent).toContain(NOTICE);
  });

  it("says a missing or someone else's request doesn't exist, and offers another account", async () => {
    api.inputs.get.mockRejectedValue(new ApiError(404, "not_found", "Not found"));
    auth.logout.mockResolvedValue(undefined);
    const el = await render();
    expect(el.textContent).toContain("This request doesn't exist");
    expect(el.textContent).toContain("Signed in as member@example.com");
    const button = [...el.querySelectorAll("button")].find((b) => b.textContent === "Sign in with a different account")!;
    await act(async () => button.click());
    await settle();
    expect(auth.logout).toHaveBeenCalledTimes(1);
    expect(el.querySelector("#login-probe")?.textContent).toBe("/login?redirect=%2Finput%2Freq1");
  });

  it.each([
    ["expired", "This request has expired"],
    ["submitted", "Already filled in"],
    ["consumed", "Already filled in"],
    ["cancelled", "This request was cancelled"],
  ] as const)("shows a plain message when %s", async (status, text) => {
    api.inputs.get.mockResolvedValue(request({ status }));
    const el = await render();
    expect(el.textContent).toContain(text);
    expect(el.querySelector("form")).toBeNull();
  });

  it("trusts the server's pending status even if the device clock is past the expiry", async () => {
    api.inputs.get.mockResolvedValue(request({ expires_at: new Date(Date.now() - 60_000).toISOString() }));
    const el = await render();
    expect(el.querySelector("form")).not.toBeNull();
    expect(el.textContent).not.toContain("This request has expired");
  });
});
