import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { errorMessage, isApiError } from "../../api/client";
import { api } from "../../api/endpoints";
import { useProviders } from "../../api/hooks";
import { AuthShell } from "../../components/layout/AppLayout";
import { Button } from "../../components/ui/Button";
import { Field, Input } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { oauthErrorMessage } from "../../lib/oauthErrors";
import { safeRedirect } from "../../lib/safeRedirect";
import { OAuthButtons, OrDivider } from "./OAuthButtons";

export function LoginPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const redirect = safeRedirect(params.get("redirect"));
  const urlError = oauthErrorMessage(params.get("error"));
  const providers = useProviders();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const login = useMutation({
    mutationFn: api.auth.login,
    onSuccess: () => navigate(redirect, { replace: true }),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ email: email.trim(), password });
  };

  const loginError = login.error
    ? isApiError(login.error)
      ? (oauthErrorMessage(login.error.code) ?? login.error.message)
      : errorMessage(login.error)
    : null;

  const signupHref = `/signup${redirect !== "/" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`;
  const anyProvider = providers.data?.google || providers.data?.github;

  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1 text-sm text-muted">Welcome back to your Deployer instance.</p>

      <div className="mt-6 space-y-4">
        {urlError && <Alert tone="danger">{urlError}</Alert>}

        {anyProvider && (
          <>
            <OAuthButtons providers={providers.data} redirect={redirect} />
            <OrDivider />
          </>
        )}

        <form className="space-y-4" onSubmit={onSubmit}>
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
          <Field label="Password">
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
          {loginError && <Alert tone="danger">{loginError}</Alert>}
          <Button type="submit" variant="primary" className="w-full justify-center" loading={login.isPending}>
            Sign in
          </Button>
        </form>

        {providers.data?.allow_signup && (
          <p className="text-center text-sm text-muted">
            New here?{" "}
            <Link to={signupHref} className="font-medium text-accent hover:underline">
              Create an account
            </Link>
          </p>
        )}
      </div>
    </AuthShell>
  );
}
