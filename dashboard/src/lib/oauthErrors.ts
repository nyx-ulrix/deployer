const MESSAGES: Record<string, string> = {
  oauth_failed: "Sign-in with the provider failed. Please try again.",
  oauth_state_invalid:
    "Sign-in has to start and finish at the same Deployer address, in the same browser. Open Deployer at {url} and try again.",
  not_initialized: "This Deployer instance isn't set up yet. The owner has to finish the setup wizard first.",
  account_exists_link_required:
    "An account with this email already exists. Sign in with your password or the provider you used before, then link this one in Settings → Account.",
  identity_in_use: "That provider account is already linked to a different Deployer user.",
  signup_disabled: "Sign-up is disabled on this Deployer instance. Ask the owner for an invite.",
  provider_not_configured: "That sign-in provider isn't configured on this Deployer instance yet.",
  email_not_verified: "Your provider account's email address isn't verified. Verify it with the provider and try again.",
  invalid_credentials: "Wrong email or password.",
  rate_limited: "Too many attempts. Please wait a few minutes and try again.",
  invite_email_mismatch: "This invite is for a different email address. Sign in with the invited account.",
  invite_invalid: "This invite link has expired or was already used. Ask the person who invited you for a new link.",
  github_connect_user_mismatch:
    "This browser is signed in to Deployer as someone else (or not at all). Sign in as yourself here and connect GitHub again.",
};

/** `publicUrl` (from /setup/status) names the address sign-in must start from; defaults to this page's. */
export function oauthErrorMessage(code: string | null | undefined, publicUrl?: string | null): string | null {
  if (!code) return null;
  const text = MESSAGES[code] ?? `Sign-in failed (${code}).`;
  return text.replace("{url}", publicUrl || window.location.origin);
}

export const PROVIDER_LABELS = { google: "Google", github: "GitHub" } as const;
