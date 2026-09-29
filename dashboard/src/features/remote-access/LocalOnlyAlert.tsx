import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useCurrentUser } from "../../auth/auth-context";
import { Alert } from "../../components/ui/States";

/** A-020: shown when the public URL is localhost, so links built from it only open on this PC. */
export function LocalOnlyAlert({ children }: { children: ReactNode }) {
  const user = useCurrentUser();
  return (
    <Alert tone="warning">
      {children} Turn on Remote access (Settings &gt; Domains &amp; remote access) first
      {user.is_instance_owner ? (
        <>
          :{" "}
          <Link to="/settings/remote-access" className="font-medium text-accent hover:underline">
            Open Domains &amp; remote access
          </Link>
        </>
      ) : (
        " — ask the instance owner."
      )}
    </Alert>
  );
}
