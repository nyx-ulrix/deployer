import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailPlus, Trash2, UserMinus } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { Invite, InviteRole, Member } from "../../api/types";
import { useCurrentUser } from "../../auth/auth-context";
import { Avatar } from "../../components/layout/Brand";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, EmptyState, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { formatDate, formatDateTime } from "../../lib/format";
import { hasRole, ROLE_DESCRIPTIONS, ROLE_LABELS } from "../../lib/roles";
import { useProjectContext } from "./project-context";

const ASSIGNABLE: InviteRole[] = ["admin", "developer", "viewer"];

const COHOST_HINT =
  "Co-hosts may keep a live, two-way copy of this project's databases on their own PC (a host device they attach). " +
  "They never see the project's secrets. Needs the Developer role or higher.";

export function MembersTab() {
  const { project, can } = useProjectContext();
  return (
    <div className="space-y-5">
      <MembersCard />
      {can("admin") && <InvitesCard projectId={project.id} />}
    </div>
  );
}

function MembersCard() {
  const { project, can } = useProjectContext();
  const me = useCurrentUser();
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const members = useQuery({ queryKey: qk.members(project.id), queryFn: () => api.members.list(project.id) });
  const [removing, setRemoving] = useState<Member | null>(null);
  const [stopCohost, setStopCohost] = useState<Member | null>(null);

  const updateRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: InviteRole }) =>
      api.members.update(project.id, userId, role),
    onSuccess: (m) => {
      queryClient.setQueryData<Member[]>(qk.members(project.id), (list) =>
        list?.map((x) => (x.user_id === m.user_id ? m : x)),
      );
      toast.success(`${m.display_name || m.email} is now ${ROLE_LABELS[m.role]}.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't change role"),
  });

  // COHOSTING.md "Roles": switching it off pauses the member's copies (the API does that).
  const setCohost = useMutation({
    mutationFn: ({ userId, value }: { userId: string; value: boolean }) =>
      api.cohosting.setMemberCohost(project.id, userId, value),
    onSuccess: (m) => {
      queryClient.setQueryData<Member[]>(qk.members(project.id), (list) =>
        list?.map((x) => (x.user_id === m.user_id ? m : x)),
      );
      void queryClient.invalidateQueries({ queryKey: qk.dataSources(project.id) });
      void queryClient.invalidateQueries({ queryKey: qk.cohostEligibility(project.id) });
      setStopCohost(null);
      const name = m.display_name || m.email;
      toast.success(m.can_cohost ? `${name} can now co-host.` : `${name} can no longer co-host; their copies are paused.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't change co-hosting"),
  });

  // Mirrors the API: admins+ change it for developer+ members; the owner's and other admins' only by the owner.
  const cohostEditable = (m: Member) =>
    can("admin") &&
    hasRole(m.role, "developer") &&
    (project.my_role === "owner" || m.role === "developer" || m.user_id === me.id);

  const remove = useMutation({
    mutationFn: (m: Member) => api.members.remove(project.id, m.user_id),
    onSuccess: (_d, m) => {
      setRemoving(null);
      if (m.user_id === me.id) {
        void queryClient.invalidateQueries({ queryKey: qk.projects });
        toast.success(`You left ${project.name}.`);
        navigate("/", { replace: true });
        return;
      }
      queryClient.setQueryData<Member[]>(qk.members(project.id), (list) => list?.filter((x) => x.user_id !== m.user_id));
      toast.success(`${m.display_name || m.email} removed.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't remove member"),
  });

  return (
    <Card title="Members" description="People with access to this project." bodyClassName="p-0 sm:p-0">
      {members.isPending ? (
        <PageSpinner />
      ) : members.isError ? (
        <ErrorState className="m-4 border-0" error={members.error} onRetry={() => void members.refetch()} />
      ) : (
        <ul className="divide-y divide-border">
          {members.data.map((m) => {
            const isMe = m.user_id === me.id;
            const editable = can("admin") && m.role !== "owner" && !isMe;
            return (
              <li key={m.user_id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
                <Avatar name={m.display_name || m.email} src={m.avatar_url} />
                <div className="min-w-0 flex-1">
                  <p className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
                    <span className="truncate">{m.display_name || m.email}</span>
                    {isMe && <span className="text-xs font-normal text-muted">(you)</span>}
                    {m.can_cohost && (
                      <Badge tone="info" title={COHOST_HINT}>
                        Co-host
                      </Badge>
                    )}
                  </p>
                  <p className="truncate text-xs text-muted">
                    {m.email} · joined {formatDate(m.created_at)}
                  </p>
                </div>
                {cohostEditable(m) && (
                  <span title={COHOST_HINT}>
                    <Checkbox
                      label="Co-host"
                      checked={Boolean(m.can_cohost)}
                      disabled={setCohost.isPending}
                      aria-label={`Allow ${m.email} to co-host`}
                      onChange={(e) =>
                        e.target.checked ? setCohost.mutate({ userId: m.user_id, value: true }) : setStopCohost(m)
                      }
                    />
                  </span>
                )}
                {editable ? (
                  <Select
                    className="h-9 w-auto"
                    value={m.role}
                    aria-label={`Role for ${m.email}`}
                    disabled={updateRole.isPending}
                    onChange={(e) => updateRole.mutate({ userId: m.user_id, role: e.target.value as InviteRole })}
                  >
                    {ASSIGNABLE.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABELS[r]}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Badge tone={m.role === "owner" ? "accent" : "neutral"} title={ROLE_DESCRIPTIONS[m.role]}>
                    {ROLE_LABELS[m.role]}
                  </Badge>
                )}
                {m.role !== "owner" && (can("admin") || isMe) && (
                  <Button
                    size="icon"
                    variant="ghost"
                    className="text-danger"
                    aria-label={isMe ? "Leave project" : `Remove ${m.email}`}
                    title={isMe ? "Leave project" : "Remove member"}
                    onClick={() => setRemoving(m)}
                  >
                    <UserMinus className="size-4" />
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {stopCohost && (
        <ConfirmDialog
          open
          onClose={() => setStopCohost(null)}
          onConfirm={() => setCohost.mutate({ userId: stopCohost.user_id, value: false })}
          loading={setCohost.isPending}
          title={`Stop co-hosting for ${stopCohost.display_name || stopCohost.email}?`}
          description="Their copies stop syncing (paused). The data already on their PC stays there until the copy is removed on the Databases tab."
          confirmLabel="Stop co-hosting"
        />
      )}
      {removing && (
        <ConfirmDialog
          open
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing)}
          loading={remove.isPending}
          title={removing.user_id === me.id ? `Leave ${project.name}?` : `Remove ${removing.display_name || removing.email}?`}
          description={
            removing.user_id === me.id
              ? "You'll lose access to this project until someone invites you again."
              : "They'll immediately lose access to this project."
          }
          confirmLabel={removing.user_id === me.id ? "Leave project" : "Remove"}
        />
      )}
    </Card>
  );
}

function InvitesCard({ projectId }: { projectId: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const invites = useQuery({ queryKey: qk.invites(projectId), queryFn: () => api.invites.list(projectId) });
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<Invite | null>(null);

  const revoke = useMutation({
    mutationFn: (inv: Invite) => api.invites.revoke(projectId, inv.id),
    onSuccess: (_d, inv) => {
      queryClient.setQueryData<Invite[]>(qk.invites(projectId), (list) => list?.filter((x) => x.id !== inv.id));
      setRevoking(null);
      toast.success("Invite revoked.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't revoke invite"),
  });

  return (
    <Card
      title="Pending invites"
      description="Invite links are single-use and expire."
      actions={
        <Button variant="primary" size="sm" icon={<MailPlus className="size-4" />} onClick={() => setCreating(true)}>
          Invite
        </Button>
      }
      bodyClassName="p-0 sm:p-0"
    >
      {invites.isPending ? (
        <PageSpinner />
      ) : invites.isError ? (
        <ErrorState className="m-4 border-0" error={invites.error} onRetry={() => void invites.refetch()} />
      ) : invites.data.length === 0 ? (
        <EmptyState className="m-4" title="No pending invites" description="Create an invite link and share it with a collaborator." />
      ) : (
        <ul className="divide-y divide-border">
          {invites.data.map((inv) => (
            <li key={inv.id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{inv.email ?? "Anyone with the link"}</p>
                <p className="text-xs text-muted">Expires {formatDateTime(inv.expires_at)}</p>
              </div>
              <Badge>{ROLE_LABELS[inv.role]}</Badge>
              <Button
                size="icon"
                variant="ghost"
                className="text-danger"
                aria-label="Revoke invite"
                title="Revoke invite"
                onClick={() => setRevoking(inv)}
              >
                <Trash2 className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {creating && <CreateInviteDialog projectId={projectId} onClose={() => setCreating(false)} />}
      {revoking && (
        <ConfirmDialog
          open
          onClose={() => setRevoking(null)}
          onConfirm={() => revoke.mutate(revoking)}
          loading={revoke.isPending}
          title="Revoke invite?"
          description="The invite link will stop working immediately."
          confirmLabel="Revoke"
        />
      )}
    </Card>
  );
}

function CreateInviteDialog({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteRole>("developer");
  const [days, setDays] = useState(7);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.invites.create(projectId, { email: email.trim() || undefined, role, expires_in_days: days }),
    onSuccess: (res) => {
      setInviteUrl(res.invite_url);
      queryClient.setQueryData<Invite[]>(qk.invites(projectId), (list) => (list ? [res.invite, ...list] : [res.invite]));
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  if (inviteUrl) {
    return (
      <Dialog
        open
        onClose={onClose}
        title="Invite link created"
        footer={
          <Button variant="primary" onClick={onClose}>
            Done
          </Button>
        }
      >
        <div className="space-y-3">
          <Alert tone="warning">Copy this link now — it won't be shown again. Send it to the person you're inviting.</Alert>
          <CopyField label="Invite link" value={inviteUrl} />
          <p className="text-xs text-muted">
            {email.trim() ? `Only ${email.trim()} can accept it. ` : "Anyone with this link can join. "}
            It expires in {days} day{days === 1 ? "" : "s"}.
          </p>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="Invite to project"
      dismissible={!create.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="create-invite" variant="primary" loading={create.isPending}>
            Create invite link
          </Button>
        </>
      }
    >
      <form id="create-invite" className="space-y-4" onSubmit={onSubmit}>
        <Field label="Email" optional hint="If set, only this email address can accept the invite.">
          {(id) => (
            <Input id={id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Role" hint={ROLE_DESCRIPTIONS[role]}>
            {(id) => (
              <Select id={id} value={role} onChange={(e) => setRole(e.target.value as InviteRole)}>
                {ASSIGNABLE.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Expires after">
            {(id) => (
              <Select id={id} value={days} onChange={(e) => setDays(Number(e.target.value))}>
                {[1, 3, 7, 14, 30].map((d) => (
                  <option key={d} value={d}>
                    {d} day{d === 1 ? "" : "s"}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      </form>
    </Dialog>
  );
}
