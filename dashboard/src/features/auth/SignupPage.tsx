import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { errorMessage } from "../../api/client";
import { api } from "../../api/endpoints";
import { useProviders } from "../../api/hooks";
import { AuthShell } from "../../components/layout/AppLayout";
import { Button } from "../../components/ui/Button";
import { Field, Input } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert } from "../../components/ui/States";
import { safeRedirect } from "../../lib/safeRedirect";
import { MIN_PASSWORD } from "../../lib/constants";
import { OAuthButtons, OrDivider } from "./OAuthButtons";

export function SignupPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const inviteToken = params.get("invite") ?? undefined;
  const redirect = safeRedirect(params.get("redirect"), inviteToken ? `/invite/${inviteToken}` : "/");
  const providers = useProviders();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && password !== confirm;

  const signup = useMutation({
    mutationFn: api.auth.signup,
    onSuccess: () => navigate(redirect, { replace: true }),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirm) return;
    signup.mutate({
      email: email.trim(),
      password,
      display_name: displayName.trim() || undefined,
      invite_token: inviteToken,
    });
  };

  const loginHref = `/login${redirect !== "/" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`;

  if (providers.isPending) {
    return (
      <AuthShell>
        <PageSpinner />
      </AuthShell>
    );
  }

  const allowed = Boolean(providers.data?.allow_signup || inviteToken);

  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold tracking-tight">Create account</h1>
      <p className="mt-1 text-sm text-muted">
        {inviteToken ? "Create an account to accept your invite." : "Join this Deployer instance."}
      </p>

      <div className="mt-6 space-y-4">
        {!allowed ? (
          <Alert tone="warning" title="Sign-up is disabled">
            The owner of this Deployer instance has turned off open sign-up. Ask them for an invite link.
          </Alert>
        ) : (
          <>
            {(providers.data?.google || providers.data?.github) && (
              <>
                <OAuthButtons providers={providers.data} redirect={redirect} inviteToken={inviteToken} />
                <OrDivider />
              </>
            )}
            <form className="space-y-4" onSubmit={onSubmit}>
              <Field label="Name" optional>
                {(id) => (
                  <Input
                    id={id}
                    autoComplete="name"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                  />
                )}
              </Field>
              <Field label="Email">
                {(id) => (
                  <Input
                    id={id}
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                )}
              </Field>
              <Field label="Password" hint={`At least ${MIN_PASSWORD} characters.`}>
                {(id) => (
                  <Input
                    id={id}
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={MIN_PASSWORD}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                )}
              </Field>
              <Field label="Confirm password" error={mismatch ? "Passwords don't match." : undefined}>
                {(id) => (
                  <Input
                    id={id}
                    type="password"
                    autoComplete="new-password"
                    required
                    aria-invalid={mismatch}
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                )}
              </Field>
              {signup.error && <Alert tone="danger">{errorMessage(signup.error)}</Alert>}
              <Button
                type="submit"
                variant="primary"
                className="w-full justify-center"
                loading={signup.isPending}
                disabled={mismatch}
              >
                Create account
              </Button>
            </form>
          </>
        )}
        <p className="text-center text-sm text-muted">
          Already have an account?{" "}
          <Link to={loginHref} className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </AuthShell>
  );
}
