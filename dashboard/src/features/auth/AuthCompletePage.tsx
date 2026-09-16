import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth/auth-context";
import { AuthShell } from "../../components/layout/AppLayout";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert } from "../../components/ui/States";
import { safeRedirect } from "../../lib/safeRedirect";

/** Landing page after a successful OAuth sign-in: exchange the refresh cookie for a session. */
export function AuthCompletePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { status, refreshSession } = useAuth();
  const redirect = safeRedirect(params.get("redirect"));
  const attempted = useRef(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (status === "authenticated") {
      navigate(redirect, { replace: true });
      return;
    }
    if (status === "anonymous" && !attempted.current) {
      attempted.current = true;
      void refreshSession().then((user) => {
        if (!user) setFailed(true);
      });
    }
  }, [status, redirect, navigate, refreshSession]);

  return (
    <AuthShell>
      {failed ? (
        <div className="space-y-4">
          <Alert tone="danger" title="Couldn't finish signing in">
            Your session could not be established. This can happen if cookies are blocked or the sign-in link
            expired.
          </Alert>
          <Link to="/login" className="block text-center text-sm font-medium text-accent hover:underline">
            Back to sign in
          </Link>
        </div>
      ) : (
        <PageSpinner label="Finishing sign-in…" />
      )}
    </AuthShell>
  );
}
