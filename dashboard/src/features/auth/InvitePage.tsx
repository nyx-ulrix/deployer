import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import { errorMessage, isApiError } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useProviders } from "../../api/hooks";
import { useAuth } from "../../auth/auth-context";
import { AuthShell } from "../../components/layout/AppLayout";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { formatDateTime } from "../../lib/format";
import { oauthErrorMessage } from "../../lib/oauthErrors";
import { ROLE_DESCRIPTIONS, ROLE_LABELS } from "../../lib/roles";
import { OAuthButtons, OrDivider } from "./OAuthButtons";

export function InvitePage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { status, user, logout } = useAuth();
  const providers = useProviders();
  const preview = useQuery({
    queryKey: qk.invite(token),
    queryFn: () => api.invites.preview(token),
    retry: false,
  });

  const accept = useMutation({
    mutationFn: () => api.invites.accept(token),
    onSuccess: async ({ project_id }) => {
      await queryClient.invalidateQueries({ queryKey: qk.projects });
      toast.success(`You joined ${preview.data?.project_name ?? "the project"}.`);
      navigate(`/projects/${project_id}`, { replace: true });
    },
  });

  const here = `/invite/${encodeURIComponent(token)}`;

  if (preview.isPending) {
    return (
      <AuthShell>
        <PageSpinner />
      </AuthShell>
    );
  }

  if (preview.isError) {
    const notFound = isApiError(preview.error) && preview.error.status === 404;
    return (
      <AuthShell>
        <Alert tone="danger" title={notFound ? "This invite isn't valid" : "Couldn't load the invite"}>
          {notFound
            ? "The link may have expired, been revoked, or already been used. Ask the project admin for a new one."
            : errorMessage(preview.error)}
        </Alert>
        <Link to="/" className="mt-4 block text-center text-sm font-medium text-accent hover:underline">
          Go to Deployer
        </Link>
      </AuthShell>
    );
  }

  const invite = preview.data;
  const acceptError = accept.error
    ? isApiError(accept.error)
      ? (oauthErrorMessage(accept.error.code === "invite_email_mismatch" ? accept.error.code : null) ??
        accept.error.message)
      : errorMessage(accept.error)
    : null;

  return (
    <AuthShell>
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
        <div className="mb-4 flex size-11 items-center justify-center rounded-full bg-accent-soft text-accent">
          <MailCheck className="size-5" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">You're invited to {invite.project_name}</h1>
        <p className="mt-1 text-sm text-muted">
          {invite.invited_by_name ? `${invite.invited_by_name} invited you` : "You've been invited"} to join as{" "}
          <Badge tone="accent">{ROLE_LABELS[invite.role]}</Badge>
        </p>
        <p className="mt-2 text-xs text-muted">{ROLE_DESCRIPTIONS[invite.role]}</p>
        <dl className="mt-4 space-y-1 text-sm">
          {invite.email && (
            <div className="flex justify-between gap-3">
              <dt className="text-muted">For</dt>
              <dd className="truncate font-medium">{invite.email}</dd>
            </div>
          )}
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Expires</dt>
            <dd>{formatDateTime(invite.expires_at)}</dd>
          </div>
        </dl>
      </div>

      <div className="mt-5 space-y-4">
        {status === "authenticated" && user ? (
          <>
            <p className="text-center text-sm text-muted">
              Signed in as <span className="font-medium text-fg">{user.email}</span>
            </p>
            {acceptError && <Alert tone="danger">{acceptError}</Alert>}
            <Button
              variant="primary"
              className="w-full justify-center"
              loading={accept.isPending}
              onClick={() => accept.mutate()}
            >
              Accept invite
            </Button>
            <button
              type="button"
              className="block w-full text-center text-sm text-muted hover:text-fg"
              onClick={() => void logout()}
            >
              Use a different account
            </button>
          </>
        ) : (
          <>
            <OAuthButtons providers={providers.data} redirect={here} inviteToken={token} />
            {(providers.data?.google || providers.data?.github) && <OrDivider />}
            <div className="grid grid-cols-2 gap-2">
              <Button
                className="justify-center"
                onClick={() => navigate(`/login?redirect=${encodeURIComponent(here)}`)}
              >
                Sign in
              </Button>
              <Button
                variant="primary"
                className="justify-center"
                onClick={() => {
                  const p = new URLSearchParams({ invite: token, redirect: here });
                  if (invite.email) p.set("email", invite.email);
                  navigate(`/signup?${p.toString()}`);
                }}
              >
                Create account
              </Button>
            </div>
          </>
        )}
      </div>
    </AuthShell>
  );
}
