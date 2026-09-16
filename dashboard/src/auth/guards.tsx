import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useSetupStatus } from "../api/hooks";
import { PageSpinner } from "../components/ui/Spinner";
import { ErrorState } from "../components/ui/States";
import { safeRedirect } from "../lib/safeRedirect";
import { useAuth } from "./auth-context";

function FullPage({ children }: { children: ReactNode }) {
  return <div className="flex min-h-dvh flex-col items-center justify-center p-4">{children}</div>;
}

/** Forces `/setup` until the instance is initialized. */
export function SetupGate() {
  const location = useLocation();
  const status = useSetupStatus();
  const auth = useAuth();

  if (status.isPending || auth.status === "loading") {
    return (
      <FullPage>
        <PageSpinner label="Connecting to Deployer…" />
      </FullPage>
    );
  }
  if (status.isError) {
    return (
      <FullPage>
        <ErrorState
          className="w-full max-w-md"
          title="Can't reach the Deployer API"
          error={status.error}
          onRetry={() => void status.refetch()}
        />
      </FullPage>
    );
  }
  if (!status.data.initialized && location.pathname !== "/setup") {
    return <Navigate to="/setup" replace />;
  }
  return <Outlet />;
}

export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") {
    return (
      <FullPage>
        <PageSpinner />
      </FullPage>
    );
  }
  if (status === "anonymous") {
    const redirect = location.pathname + location.search;
    return <Navigate to={`/login?redirect=${encodeURIComponent(redirect)}`} replace />;
  }
  return <Outlet />;
}

export function RequireInstanceOwner({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!user?.is_instance_owner) {
    return (
      <ErrorState
        title="Instance owner only"
        error={new Error("Only the owner of this Deployer instance can open this page.")}
      />
    );
  }
  return <>{children}</>;
}

/** For /login and /signup: signed-in users go straight to their destination. */
export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "authenticated") {
    const params = new URLSearchParams(location.search);
    return <Navigate to={safeRedirect(params.get("redirect"))} replace />;
  }
  return <>{children}</>;
}
