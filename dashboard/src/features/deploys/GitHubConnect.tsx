import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Unlink } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { GitHubIcon } from "../../components/layout/Brand";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { PageSpinner } from "../../components/ui/Spinner";
import { Card } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { oauthErrorMessage } from "../../lib/oauthErrors";
import { safeRedirect } from "../../lib/safeRedirect";

// docs/DEPLOYMENTS.md "Connect a Git repository": GitHub's authorize page, then back to
// /integrations/github/done, which returns to the page that started it (kept here meanwhile).
const RETURN_KEY = "deployer.github.return";

/** Starts the GitHub connect flow (full-page redirect); comes back to `returnTo`. */
export function ConnectGitHubButton({ returnTo, label = "Connect GitHub" }: { returnTo: string; label?: string }) {
  const toast = useToast();
  const connect = useMutation({
    mutationFn: api.github.connect,
    onSuccess: ({ url }) => {
      try {
        sessionStorage.setItem(RETURN_KEY, returnTo);
      } catch {
        // Private mode: we come back to Account settings instead.
      }
      window.location.assign(url);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't start connecting GitHub"),
  });
  return (
    <Button variant="primary" icon={<GitHubIcon className="size-4" />} loading={connect.isPending || connect.isSuccess} onClick={() => connect.mutate()}>
      {label}
    </Button>
  );
}

/** Landing page after GitHub's redirect (`?ok=1` or `?error=code`): toast, then back to where the user was. */
export function GitHubDonePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;
    let back: string | null;
    try {
      back = sessionStorage.getItem(RETURN_KEY);
      sessionStorage.removeItem(RETURN_KEY);
    } catch {
      back = null;
    }
    const error = params.get("error");
    if (params.get("ok") === "1") toast.success("GitHub connected. Pick a repository to deploy.");
    else toast.error(oauthErrorMessage(error) ?? "Connecting GitHub failed.", "Couldn't connect GitHub");
    void queryClient.invalidateQueries({ queryKey: qk.github });
    navigate(safeRedirect(back, "/settings/account"), { replace: true });
  }, [params, navigate, toast, queryClient]);

  return <PageSpinner label="Connecting GitHub…" />;
}

/** Account settings: "GitHub: connected as <login> · Disconnect". */
export function GitHubAccountCard() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const status = useQuery({ queryKey: qk.github, queryFn: api.github.status });
  const disconnect = useMutation({
    mutationFn: api.github.disconnect,
    onSuccess: (r) => {
      setConfirming(false);
      void queryClient.invalidateQueries({ queryKey: qk.github });
      toast.success(r.message, "GitHub disconnected");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't disconnect GitHub"),
  });
  const s = status.data;
  if (!s || (!s.connected && !s.configured)) return null;

  return (
    <Card title="Repository access" description="Lets you pick a GitHub repository when creating an app; Deployer clones it and adds the push webhook for you.">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-lg border border-border bg-surface-2">
          <GitHubIcon className="size-4.5" />
        </span>
        <p className="min-w-0 flex-1 text-sm">
          {s.connected ? (
            <>
              GitHub: connected as <span className="font-medium">{s.login}</span>
            </>
          ) : (
            "GitHub: not connected"
          )}
        </p>
        {s.connected ? (
          <Button size="sm" variant="outline-danger" icon={<Unlink className="size-3.5" />} onClick={() => setConfirming(true)}>
            Disconnect
          </Button>
        ) : (
          <ConnectGitHubButton returnTo="/settings/account" />
        )}
      </div>
      {confirming && (
        <ConfirmDialog
          open
          onClose={() => setConfirming(false)}
          onConfirm={() => disconnect.mutate()}
          loading={disconnect.isPending}
          title="Disconnect GitHub?"
          description="Deployer deletes its copy of the token. Apps you created through this connection can't clone until you reconnect or give them a token; their webhooks keep working. You can also revoke access at github.com/settings/applications."
          confirmLabel="Disconnect"
        />
      )}
    </Card>
  );
}
