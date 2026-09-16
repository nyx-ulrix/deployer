import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { client } from "../api/client";
import { api } from "../api/endpoints";
import type { User } from "../api/types";
import { AuthContext, type AuthContextValue, type AuthStatus } from "./auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUserState] = useState<User | null>(null);
  const [booted, setBooted] = useState(false);
  const userIdRef = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    const unsubscribe = client.subscribe((u) => {
      const nextId = u?.id ?? null;
      // A different user (or sign-out) invalidates everything cached for the previous one.
      if (userIdRef.current !== nextId && userIdRef.current !== undefined) {
        queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "setup-status" });
      }
      userIdRef.current = nextId;
      setUserState(u);
    });
    let cancelled = false;
    void client.refresh().finally(() => {
      if (!cancelled) setBooted(true);
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [queryClient]);

  const refreshSession = useCallback(async () => {
    const res = await client.refresh();
    return res?.user ?? null;
  }, []);

  const logout = useCallback(async () => {
    await api.auth.logout();
    queryClient.clear();
  }, [queryClient]);

  const status: AuthStatus = user ? "authenticated" : booted ? "anonymous" : "loading";

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, setUser: setUserState, refreshSession, logout }),
    [status, user, refreshSession, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
