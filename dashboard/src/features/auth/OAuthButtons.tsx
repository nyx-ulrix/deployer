import { api } from "../../api/endpoints";
import type { ProviderName } from "../../api/types";
import { ProviderIcon } from "../../components/layout/Brand";
import { Button } from "../../components/ui/Button";
import { PROVIDER_LABELS } from "../../lib/oauthErrors";

export function OAuthButtons({
  providers,
  redirect,
  inviteToken,
}: {
  providers: { google: boolean; github: boolean } | undefined;
  redirect: string;
  inviteToken?: string;
}) {
  const enabled = (["google", "github"] as ProviderName[]).filter((p) => providers?.[p]);
  if (enabled.length === 0) return null;
  return (
    <div className="space-y-2">
      {enabled.map((p) => (
        <Button
          key={p}
          className="w-full justify-center"
          icon={<ProviderIcon provider={p} />}
          onClick={() => window.location.assign(api.auth.oauthStartUrl(p, redirect, inviteToken))}
        >
          Continue with {PROVIDER_LABELS[p]}
        </Button>
      ))}
    </div>
  );
}

export function OrDivider() {
  return (
    <div className="flex items-center gap-3 text-xs text-muted uppercase">
      <span className="h-px flex-1 bg-border" />
      or
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}
