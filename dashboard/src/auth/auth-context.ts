import { createContext, useContext } from "react";
import type { User } from "../api/types";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  /** Replace the cached user (e.g. after PATCH /auth/me). */
  setUser: (user: User) => void;
  /** Try to obtain a session from the refresh cookie (e.g. after OAuth). */
  refreshSession: () => Promise<User | null>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** For components rendered only behind RequireAuth. */
export function useCurrentUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("useCurrentUser used without an authenticated user");
  return user;
}
