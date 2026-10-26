import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { CliToken } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Card, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { formatDateTime, relativeTime } from "../../lib/format";

/** The `deployer login` tokens of this account (docs/CLI.md). */
export function CliTokensCard() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [revoking, setRevoking] = useState<CliToken | null>(null);
  const tokens = useQuery({ queryKey: qk.cliTokens, queryFn: api.auth.cliTokens });

  const revoke = useMutation({
    mutationFn: (t: CliToken) => api.auth.revokeCliToken(t.id),
    onSuccess: (_ok, t) => {
      setRevoking(null);
      toast.success(`${t.name} is signed out.`);
      void queryClient.invalidateQueries({ queryKey: qk.cliTokens });
    },
    onError: (e) => {
      setRevoking(null);
      toast.error(errorMessage(e), "Couldn't revoke the token");
    },
  });

  return (
    <Card
      title="Command-line sign-ins"
      description="Servers where you ran deployer login and approved the code. Each one acts as you until revoked."
      bodyClassName="p-0 sm:p-0"
    >
      {tokens.isError ? (
        <div className="p-4 sm:p-5">
          <ErrorAlert error={tokens.error} />
        </div>
      ) : tokens.data && tokens.data.length > 0 ? (
        <ul className="divide-y divide-border">
          {tokens.data.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{t.name}</p>
                <p className="text-xs text-muted">
                  <span title={formatDateTime(t.created_at)}>Approved {relativeTime(t.created_at)}</span> ·{" "}
                  {t.last_used_at ? (
                    <span title={formatDateTime(t.last_used_at)}>last used {relativeTime(t.last_used_at)}</span>
                  ) : (
                    "not used yet"
                  )}
                </p>
              </div>
              <Button size="sm" variant="outline-danger" onClick={() => setRevoking(t)}>
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-4 py-4 text-sm text-muted sm:px-5">
          {tokens.isPending ? "Loading…" : (
            <>
              None yet. On a server, run <code>deployer login</code> and open the link it prints.
            </>
          )}
        </p>
      )}
      {revoking && (
        <ConfirmDialog
          open
          onClose={() => setRevoking(null)}
          onConfirm={() => revoke.mutate(revoking)}
          loading={revoke.isPending}
          title={`Revoke ${revoking.name}?`}
          description="That command line stops working at once. Run deployer login there again to sign it back in."
          confirmLabel="Revoke"
        />
      )}
    </Card>
  );
}
