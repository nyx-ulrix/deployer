import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Cloud, RefreshCw, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useProjects } from "../../api/hooks";
import type { CloudConnection, CloudProvider } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { ExtLink } from "../../components/ui/ExtLink";
import { Field, Input, Select, Textarea } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, ErrorAlert, ErrorState, PageHeader } from "../../components/ui/States";
import { StepCard, type StepStatus } from "../../components/ui/StepCard";
import { Tabs } from "../../components/ui/Tabs";
import { useToast } from "../../components/ui/toast-context";
import { InstanceNav } from "./InstanceNav";
import { deriveSigninSteps } from "./signinSteps";

/**
 * docs/CLOUD.md "Cloud connections": the owner connects their own AWS / Firebase accounts (guided, like the
 * sign-in apps), Deployer validates them and never shows the keys again. Apps then pick a cloud target.
 */
export function CloudAccountsPage() {
  const [provider, setProvider] = useState<CloudProvider>("aws");
  const list = useQuery({ queryKey: qk.cloudConnections, queryFn: api.cloud.list });
  const requirements = useQuery({ queryKey: qk.cloudRequirements, queryFn: api.cloud.requirements, staleTime: Infinity });

  return (
    <div className="mx-auto w-full max-w-4xl">
      <InstanceNav />
      <PageHeader
        title="Cloud accounts"
        description="Connect your own AWS or Firebase / Google Cloud account so apps can run entirely in the cloud and keep serving when this PC is off."
      />
      <div className="space-y-5">
        <Alert tone="info" title="Billed to your account">
          AWS and Google bill whatever the cloud targets use (storage, traffic, running services) directly to the account you connect —
          nothing goes through Deployer. Each target in an app's settings explains its cost drivers; both providers have free tiers, and
          deleting an app removes what Deployer created.
        </Alert>
        {list.isPending ? (
          <PageSpinner />
        ) : list.isError ? (
          <ErrorState error={list.error} onRetry={() => void list.refetch()} />
        ) : (
          <ConnectionsCard connections={list.data.connections} />
        )}
        <Card title="Connect an account">
          <Tabs<CloudProvider>
            value={provider}
            onChange={setProvider}
            items={[
              { value: "aws", label: "AWS", icon: <Cloud className="size-4" /> },
              { value: "firebase", label: "Firebase / Google Cloud", icon: <Cloud className="size-4" /> },
            ]}
          />
          <div className="mt-4 space-y-3">
            {requirements.isError && <ErrorAlert error={requirements.error} />}
            {provider === "aws" ? (
              <AwsGuide policy={requirements.data ? JSON.stringify(requirements.data.aws.policy, null, 2) : ""} />
            ) : (
              <FirebaseGuide roles={requirements.data?.firebase.roles ?? []} apis={requirements.data?.firebase.apis ?? []} />
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function ConnectionsCard({ connections }: { connections: CloudConnection[] }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const projects = useProjects();
  const [removing, setRemoving] = useState<CloudConnection | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: qk.cloudConnections });
  const check = useMutation({
    mutationFn: (c: CloudConnection) => api.cloud.check(c.id),
    onSuccess: (c) => {
      void refresh();
      if (c.status === "ok") toast.success(`${c.name} works.`);
      else toast.error(c.status_message ?? "The credentials were not accepted", c.name);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't check"),
  });
  const remove = useMutation({
    mutationFn: (c: CloudConnection) => api.cloud.remove(c.id),
    onSuccess: () => {
      setRemoving(null);
      void refresh();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't remove"),
  });
  const projectName = (id: string | null) =>
    id ? (projects.data?.find((p) => p.id === id)?.name ?? "one project") : "every project";

  return (
    <Card title="Connected accounts">
      {connections.length === 0 ? (
        <p className="text-sm text-muted">None yet. Follow a guide below; it takes about five minutes.</p>
      ) : (
        <ul className="divide-y divide-border">
          {connections.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm">
              <Badge tone="info">{c.provider === "aws" ? "AWS" : "Firebase"}</Badge>
              <span className="font-medium">{c.name}</span>
              <span className="font-mono text-xs text-muted">
                {c.provider === "aws"
                  ? `account ${c.account.account_id} · ${c.account.region} · key …${c.account.access_key_id_last4}`
                  : `${c.account.project_id} · ${c.account.region}`}
              </span>
              <span className="text-xs text-muted">for {projectName(c.project_id)}</span>
              <Badge tone={c.status === "ok" ? "success" : "danger"} title={c.status_message ?? undefined}>
                {c.status === "ok" ? "Working" : "Failing"}
              </Badge>
              {c.apps_using ? <span className="text-xs text-muted">{c.apps_using} app(s)</span> : null}
              <span className="ml-auto flex gap-1">
                <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} loading={check.isPending} onClick={() => check.mutate(c)}>
                  Check
                </Button>
                <Button size="icon-sm" variant="ghost" aria-label={`Remove ${c.name}`} onClick={() => setRemoving(c)}>
                  <Trash2 className="size-4" />
                </Button>
              </span>
              {c.status_message && <p className="w-full text-xs text-danger">{c.status_message}</p>}
            </li>
          ))}
        </ul>
      )}
      {removing && (
        <ConfirmDialog
          open
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing)}
          loading={remove.isPending}
          title={`Remove ${removing.name}?`}
          description="Deployer forgets the credentials. Apps still using it must move to another target first (that removes their cloud resources). Also delete the key in the AWS / Google console if you no longer need it."
          confirmLabel="Remove"
        />
      )}
    </Card>
  );
}

function DoneButton({ status, onClick }: { status: StepStatus; onClick: () => void }) {
  if (status === "done") return null;
  return (
    <Button size="sm" variant="primary" icon={<Check className="size-4" />} onClick={onClick}>
      I've done this
    </Button>
  );
}

/** Guide state: console steps are marked done by the user; the paste step stays open. */
function useGuide(count: number) {
  const [acknowledged, setAcknowledged] = useState<number[]>([]);
  const steps = deriveSigninSteps(count, { configured: false, clientIdSaved: false, acknowledged });
  return { steps, ack: (i: number) => setAcknowledged((a) => [...a, i]) };
}

function ScopeField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const projects = useProjects();
  return (
    <Field label="Who may use it" hint="Project admins pick it for their apps. Limit it to one project to keep costs separate.">
      {(id) => (
        <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">Every project</option>
          {(projects.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              Only {p.name}
            </option>
          ))}
        </Select>
      )}
    </Field>
  );
}

function useCreate(onDone: () => void) {
  const toast = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.cloud.create,
    onSuccess: (c) => {
      void queryClient.invalidateQueries({ queryKey: qk.cloudConnections });
      toast.success(`${c.name} connected and validated.`);
      onDone();
    },
  });
}

const AWS_TITLES = ["Create an IAM user for Deployer", "Give it exactly the permissions it needs", "Create an access key", "Paste and validate"];

function AwsGuide({ policy }: { policy: string }) {
  const { steps, ack } = useGuide(AWS_TITLES.length);
  const [form, setForm] = useState({ name: "AWS", access_key_id: "", secret_access_key: "", region: "us-east-1", role_arn: "", project_id: "" });
  const create = useCreate(() => setForm((f) => ({ ...f, access_key_id: "", secret_access_key: "" })));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({
      provider: "aws",
      name: form.name.trim() || "AWS",
      project_id: form.project_id || null,
      aws: {
        access_key_id: form.access_key_id.trim(),
        secret_access_key: form.secret_access_key.trim(),
        region: form.region.trim(),
        role_arn: form.role_arn.trim() || null,
      },
    });
  };
  const iam = "https://console.aws.amazon.com/iam/home";
  return (
    <>
      <StepCard n={1} title={AWS_TITLES[0]} status={steps[0]} summary="A separate user, no console access">
        <div className="space-y-3">
          <p className="text-muted">
            Open <ExtLink href={`${iam}#/users/create`}>IAM → Users → Create user</ExtLink>, name it <code className="font-mono">deployer</code>{" "}
            and leave <em>Provide user access to the AWS Management Console</em> unticked. A dedicated user keeps Deployer's access separate
            from yours and easy to revoke.
          </p>
          <DoneButton status={steps[0]} onClick={() => ack(0)} />
        </div>
      </StepCard>
      <StepCard n={2} title={AWS_TITLES[1]} status={steps[1]} summary="S3, CloudFront, ACM, ECR, App Runner, RDS and DynamoDB databases, deployer-* IAM roles, GitHub Actions sign-in">
        <div className="space-y-3">
          <p className="text-muted">
            Open <ExtLink href={`${iam}#/policies/create`}>IAM → Policies → Create policy</ExtLink>, switch to <strong>JSON</strong>, paste this,
            name it <code className="font-mono">DeployerHosting</code> and create it. Then open the <code className="font-mono">deployer</code>{" "}
            user → <em>Add permissions → Attach policies directly</em> → tick <code className="font-mono">DeployerHosting</code>. It only
            reaches resources named <code className="font-mono">deployer-*</code> (and firewall rules Deployer created itself). The
            one exception is reading and writing items of DynamoDB tables: tables you connect keep their own names, so Deployer may use
            the items, backups and point-in-time recovery of any table, but it only creates, changes or deletes{" "}
            <code className="font-mono">deployer-*</code> tables (a restore always makes a new one).
          </p>
          <p className="text-muted">
            Already attached an older version? Paste this one over it (<em>Edit → JSON</em>): it adds the permissions for databases in
            your AWS account (create / connect RDS and the firewall that lets this PC and your apps in; DynamoDB tables, their
            backups, point-in-time recovery and restores, and the role an App Runner app uses to reach its tables) and for building apps on GitHub Actions (GitHub&apos;s
            sign-in for your account and one <code className="font-mono">deployer-gha-*</code> role per app, which only that app&apos;s
            repository can use).
          </p>
          {policy && <CopyField label="Policy JSON" value={policy} />}
          <DoneButton status={steps[1]} onClick={() => ack(1)} />
        </div>
      </StepCard>
      <StepCard n={3} title={AWS_TITLES[2]} status={steps[2]} summary="AWS shows the secret only once">
        <div className="space-y-3">
          <p className="text-muted">
            On the user's <em>Security credentials</em> tab click <strong>Create access key</strong>, choose <em>Application running outside
            AWS</em>, and copy the <strong>Access key</strong> and <strong>Secret access key</strong>. Optionally, to use a role instead, give
            the user only <code className="font-mono">sts:AssumeRole</code> on a role that has the policy and enter its ARN below.
          </p>
          <DoneButton status={steps[2]} onClick={() => ack(2)} />
        </div>
      </StepCard>
      <StepCard n={4} title={AWS_TITLES[3]} status={steps[3]} open>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name">{(id) => <Input id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field>
            <Field label="Region" hint="Where buckets, images and App Runner services are created, e.g. us-east-1, eu-west-1.">
              {(id) => <Input id={id} value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} spellCheck={false} />}
            </Field>
            <Field label="Access key ID">
              {(id) => (
                <Input id={id} value={form.access_key_id} onChange={(e) => setForm({ ...form, access_key_id: e.target.value })} placeholder="AKIA…" autoComplete="off" spellCheck={false} />
              )}
            </Field>
            <Field label="Secret access key">
              {(id) => (
                <Input id={id} type="password" value={form.secret_access_key} onChange={(e) => setForm({ ...form, secret_access_key: e.target.value })} autoComplete="off" />
              )}
            </Field>
            <Field label="Role ARN" optional hint="Assumed for every call when set.">
              {(id) => (
                <Input id={id} value={form.role_arn} onChange={(e) => setForm({ ...form, role_arn: e.target.value })} placeholder="arn:aws:iam::<account>:role/<name>" spellCheck={false} />
              )}
            </Field>
            <ScopeField value={form.project_id} onChange={(project_id) => setForm({ ...form, project_id })} />
          </div>
          <p className="text-xs text-muted">Deployer checks the key with AWS (sts:GetCallerIdentity), stores it encrypted and never shows it again.</p>
          {create.isError && <ErrorAlert error={create.error} />}
          <Button variant="primary" type="submit" loading={create.isPending} disabled={!form.access_key_id.trim() || !form.secret_access_key.trim()}>
            Validate and connect
          </Button>
        </form>
      </StepCard>
    </>
  );
}

const FIREBASE_TITLES = [
  "Create or pick a Firebase project",
  "Turn on the APIs",
  "Create a service account with these roles",
  "Download a JSON key",
  "Paste and validate",
];

// What an API or role marked `only_for` is needed for (docs/CLOUD.md).
const ONLY_FOR: Record<string, string> = {
  firebase_app: "only needed for full apps",
  firestore: "only needed for Firestore databases",
  firebase_rtdb: "only needed for Realtime Databases",
  github_actions: "only needed to build apps on GitHub Actions",
};

function FirebaseGuide({
  roles,
  apis,
}: {
  roles: { role: string; title: string; why: string; only_for?: string; on?: string }[];
  apis: { api: string; title: string; only_for?: string }[];
}) {
  const { steps, ack } = useGuide(FIREBASE_TITLES.length);
  const [form, setForm] = useState({ name: "Firebase", json: "", region: "us-central1", project_id: "" });
  const create = useCreate(() => setForm((f) => ({ ...f, json: "" })));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({
      provider: "firebase",
      name: form.name.trim() || "Firebase",
      project_id: form.project_id || null,
      firebase: { service_account_json: form.json, region: form.region.trim() || null },
    });
  };
  const gcp = (path: string) => `https://console.cloud.google.com/${path}`;
  return (
    <>
      <div className="rounded-xl border border-border bg-surface-2 p-3 text-sm">
        <p className="font-medium">Two ways to host on Firebase — you pick per app</p>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-muted">
          <li>
            <span className="text-fg">Firebase Hosting (static)</span>: your built HTML, CSS and JavaScript on Firebase's CDN with HTTPS at{" "}
            <code className="font-mono">&lt;site&gt;.web.app</code>. For React/Vue/Vite/Astro sites. Works on the free Spark plan.
          </li>
          <li>
            <span className="text-fg">Firebase full app (Cloud Run)</span>: your Node, Python or Dockerfile server runs as a container on
            Google Cloud Run, reachable through Firebase Hosting's address. For APIs and server-rendered sites. Needs the Blaze
            (pay-as-you-go) plan; it scales to zero when nobody visits.
          </li>
          <li>
            <span className="text-fg">Cloud Firestore database</span>: connect the project&apos;s Firestore database under Databases → Add
            database → In your Firebase project, browse and edit it here, and give it to full apps. Free daily quota, then billed per read
            and write.
          </li>
          <li>
            <span className="text-fg">Realtime Database</span>: Firebase&apos;s JSON-tree database that pushes changes to apps instantly.
            Connect it (or create the project&apos;s default one) the same way, browse it as a tree here, and give it to full apps. Free
            quota, then billed per GB stored and downloaded.
          </li>
        </ul>
      </div>
      <StepCard n={1} title={FIREBASE_TITLES[0]} status={steps[0]} summary="Blaze plan only for full apps">
        <div className="space-y-3">
          <p className="text-muted">
            In the <ExtLink href="https://console.firebase.google.com/">Firebase console</ExtLink> create a project (or use one) and note its{" "}
            <strong>Project ID</strong> (Project settings). For full apps (Cloud Run) upgrade it to the Blaze plan; a budget alert in Google
            Cloud Billing is a good idea.
          </p>
          <DoneButton status={steps[0]} onClick={() => ack(0)} />
        </div>
      </StepCard>
      <StepCard n={2} title={FIREBASE_TITLES[1]} status={steps[1]} summary={`${apis.length} APIs, one click each`}>
        <div className="space-y-3">
          <p className="text-muted">Open each one for your project and click <strong>Enable</strong>:</p>
          <ul className="list-disc space-y-1 pl-5">
            {apis.map((a) => (
              <li key={a.api}>
                <ExtLink href={gcp(`apis/library/${a.api}`)}>{a.title}</ExtLink>
                {a.only_for && <span className="text-xs text-muted"> — {ONLY_FOR[a.only_for] ?? a.only_for}</span>}
              </li>
            ))}
          </ul>
          <DoneButton status={steps[1]} onClick={() => ack(1)} />
        </div>
      </StepCard>
      <StepCard n={3} title={FIREBASE_TITLES[2]} status={steps[2]} summary="A dedicated identity for Deployer">
        <div className="space-y-3">
          <p className="text-muted">
            Open <ExtLink href={gcp("iam-admin/serviceaccounts/create")}>IAM &amp; Admin → Service accounts → Create</ExtLink>, name it{" "}
            <code className="font-mono">deployer</code> and grant these roles:
          </p>
          <ul className="list-disc space-y-1 pl-5">
            {roles.map((r) => (
              <li key={r.role}>
                <span className="font-medium">{r.title}</span> <code className="font-mono text-xs text-muted">{r.role}</code>
                <span className="text-xs text-muted">
                  {" "}
                  — {r.why}
                  {r.only_for && ` (${ONLY_FOR[r.only_for] ?? r.only_for})`}
                  {r.on === "service_account" &&
                    ". Grant this one on the deployer service account itself, not the whole project: Service accounts → deployer → Permissions → Grant access → the deployer account's email → this role"}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-muted">
            Full apps that use a Firestore database run on Cloud Run as the project&apos;s default compute service account (
            <code className="font-mono text-xs">PROJECT_NUMBER-compute@developer.gserviceaccount.com</code>, listed under IAM). Grant it{" "}
            <strong>Cloud Datastore User</strong> too (and <strong>Firebase Realtime Database Admin</strong> for a Realtime Database), unless it
            already has Editor. Already made the <code className="font-mono">deployer</code> account? Add the database roles to it (IAM → Edit
            principal) and turn on the database APIs above.
          </p>
          <DoneButton status={steps[2]} onClick={() => ack(2)} />
        </div>
      </StepCard>
      <StepCard n={4} title={FIREBASE_TITLES[3]} status={steps[3]} summary="Keep the file private">
        <div className="space-y-3">
          <p className="text-muted">
            Open the service account → <strong>Keys</strong> → <em>Add key → Create new key → JSON</em>. The file downloads once; anyone with
            it can act as the account, so delete it from your Downloads after pasting it below.
          </p>
          <DoneButton status={steps[3]} onClick={() => ack(3)} />
        </div>
      </StepCard>
      <StepCard n={5} title={FIREBASE_TITLES[4]} status={steps[4]} open>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Service-account key (JSON file contents)">
            {(id) => (
              <Textarea id={id} rows={5} value={form.json} onChange={(e) => setForm({ ...form, json: e.target.value })} className="font-mono text-xs" spellCheck={false} placeholder='{"type": "service_account", ...}' />
            )}
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Name">{(id) => <Input id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field>
            <Field label="Region" hint="For Cloud Run and its images.">
              {(id) => <Input id={id} value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} spellCheck={false} />}
            </Field>
            <ScopeField value={form.project_id} onChange={(project_id) => setForm({ ...form, project_id })} />
          </div>
          <p className="text-xs text-muted">Deployer signs in with the key, looks the project up, stores the key encrypted and never shows it again.</p>
          {create.isError && <ErrorAlert error={create.error} />}
          <Button variant="primary" type="submit" loading={create.isPending} disabled={!form.json.trim()}>
            Validate and connect
          </Button>
        </form>
      </StepCard>
    </>
  );
}
