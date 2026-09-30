import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { AuthContext, type AuthContextValue } from "./auth-context";
import { SetupGate } from "./guards";

const { api } = vi.hoisted(() => ({ api: { setup: { status: vi.fn() } } }));
vi.mock("../api/endpoints", async (orig) => ({ ...(await orig<object>()), api }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("SetupGate", () => {
  it("shows 'Deployer is starting' on a 502, polls, and recovers with a fresh session", async () => {
    vi.useFakeTimers();
    api.setup.status
      .mockRejectedValueOnce(new ApiError(502, "server_error", "Bad Gateway"))
      .mockRejectedValueOnce(new ApiError(502, "server_error", "Bad Gateway"))
      .mockResolvedValue({ initialized: true, device_mode: null });
    const refreshSession = vi.fn().mockResolvedValue(null);
    const auth: AuthContextValue = {
      status: "anonymous",
      user: null,
      setUser: () => {},
      refreshSession,
      logout: async () => {},
    };
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);
    await act(async () => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <AuthContext.Provider value={auth}>
            <MemoryRouter>
              <Routes>
                <Route element={<SetupGate />}>
                  <Route path="/" element={<p>dashboard</p>} />
                </Route>
              </Routes>
            </MemoryRouter>
          </AuthContext.Provider>
        </QueryClientProvider>,
      );
    });
    await act(() => vi.advanceTimersByTimeAsync(1_500)); // the hook's one retry
    expect(el.textContent).toContain("Deployer is starting");
    expect(el.textContent).toContain("Deployer Control");
    expect(el.textContent).not.toContain("Bad Gateway");
    expect(refreshSession).not.toHaveBeenCalled();

    await act(() => vi.advanceTimersByTimeAsync(5_000)); // the poll
    expect(el.textContent).toContain("dashboard");
    expect(refreshSession).toHaveBeenCalledTimes(1);
    act(() => root.unmount());
  });
});
