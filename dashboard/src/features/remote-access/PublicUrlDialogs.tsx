import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import type { PublicUrlResponse, RemoteAccess } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { currentDomain, OAUTH_CONSOLES, remoteAccessError } from "./remoteAccess";

export function PublicUrlResultDialog({ result, onClose }: { result: PublicUrlResponse; onClose: () => void }) {
  const url = result.settings.public_url;
  const onNewAddress = (() => {
    try {
      return new URL(url).host === window.location.host;
    } catch {
      return false;
    }
  })();
  const changed = result.previous_public_url !== url;
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title="Public URL updated"
      description={changed ? `${result.previous_public_url} → ${url}` : url}
      footer={
        <>
          {!onNewAddress && (
            <a
              href={url}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-border bg-surface px-3.5 text-sm font-medium shadow-sm hover:bg-surface-2"
            >
              Open {url} <ExternalLink className="size-4" />
            </a>
          )}
          <Button variant="primary" onClick={onClose}>
            Done
          </Button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <CopyField label="New public URL" value={url} />
        <div className="space-y-3">
          <h3 className="font-semibold">Update your sign-in providers</h3>
          <p className="text-muted">
            Google and GitHub only redirect back to callback URLs you've registered. Add these in each OAuth app (you
            can keep the old ones registered during the switch), or sign-in with those providers will fail.
          </p>
          <div className="space-y-1.5">
            <CopyField label="Google — Authorized redirect URI" value={result.oauth_callbacks.google} />
            <a href={OAUTH_CONSOLES.google} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">
              Google Cloud Console → Credentials <ExternalLink className="size-3" />
            </a>
          </div>
          <div className="space-y-1.5">
            <CopyField label="GitHub — Authorization callback URL" value={result.oauth_callbacks.github} />
            <a href={OAUTH_CONSOLES.github} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">
              GitHub → Developer settings → OAuth Apps <ExternalLink className="size-3" />
            </a>
          </div>
        </div>
        <Alert tone="info" title="Host devices and invite links">
          Host devices should use the new URL — re-enroll a device if it was attached with the old address. New invite
          links use the new URL too.
        </Alert>
        {!onNewAddress && url.startsWith("https://") && (
          <Alert tone="warning" title="Sign in at the new address">
            With an https public URL, sign-in cookies are marked Secure. If you get signed out here, open the dashboard
            at {url}. To go back, open <code>http://localhost</code> on this PC and choose <em>Use local URL</em>.
          </Alert>
        )}
      </div>
    </Dialog>
  );
}

export function UnlinkDialog({ data, onClose }: { data: RemoteAccess; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [deleteDns, setDeleteDns] = useState(true);
  const [deleteTunnel, setDeleteTunnel] = useState(false);
  const via = currentDomain(data);
  const unlink = useMutation({
    mutationFn: () => api.remoteAccess.unlink({ delete_dns: deleteDns, delete_tunnel: deleteTunnel }),
    onSuccess: (res) => {
      queryClient.setQueryData(qk.remoteAccess, res);
      void queryClient.invalidateQueries({ queryKey: qk.instanceSettings });
      void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
      toast.success("Cloudflare unlinked.");
      onClose();
    },
  });
  return (
    <ConfirmDialog
      open
      onClose={onClose}
      onConfirm={() => unlink.mutate()}
      loading={unlink.isPending}
      title="Unlink Cloudflare?"
      confirmLabel="Unlink"
      description="Deployer stops the tunnel connector and forgets the API token, account and hostnames."
    >
      <div className="space-y-3">
        <Checkbox
          checked={deleteDns}
          onChange={(e) => setDeleteDns(e.target.checked)}
          label="Also delete DNS records"
          description="Only the CNAME records Deployer created."
        />
        <Checkbox
          checked={deleteTunnel}
          onChange={(e) => setDeleteTunnel(e.target.checked)}
          label="Also delete the tunnel in Cloudflare"
          description={data.cloudflare.tunnel ? `Deletes ${data.cloudflare.tunnel.name}.` : undefined}
        />
        {via && (
          <Alert tone="danger" title="You're using this page through Cloudflare">
            This page is open at {via.hostname}. Unlinking cuts that connection — continue from{" "}
            <code>http://localhost</code> on the Deployer PC.
          </Alert>
        )}
        {unlink.error && (
          <Alert tone="danger">
            {remoteAccessError(unlink.error)} Nothing was unlinked. Try again, or untick both boxes to unlink without
            touching Cloudflare.
          </Alert>
        )}
      </div>
    </ConfirmDialog>
  );
}
