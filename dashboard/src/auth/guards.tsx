import { useEffect, useRef, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { isApiStarting } from "../api/client";
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
  const starting = status.isError && isApiStarting(status.error);
  const wasStarting = useRef(false);
  const { refreshSession } = auth;

  useEffect(() => {
    if (starting) wasStarting.current = true;
    // The boot-time session refresh failed while the API was down: retry it now it's back.
    else if (status.isSuccess && wasStarting.current) {
      wasStarting.current = false;
      void refreshSession().catch(() => {});
    }
  }, [starting, status.isSuccess, refreshSession]);

  if (starting) {
    return (
      <FullPage>
        <div className="flex flex-col items-center">
          <PageSpinner label="Deployer is starting…" />
          <p className="max-w-sm text-center text-sm text-muted">
            This page reconnects on its own, usually within a minute or two after the PC starts. If it
            doesn't, open <strong>Deployer Control</strong> from the Start menu to check its status or
            restart it.
          </p>
        </div>
      </FullPage>
    );
  }
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
  // A host device has no users of its own: its dashboard only shows the device status page.
  if (status.data.device_mode === "host") {
    return location.pathname === "/device" ? <Outlet /> : <Navigate to="/device" replace />;
  }
  if (!status.data.initialized && location.pathname !== "/setup" && location.pathname !== "/device") {
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
