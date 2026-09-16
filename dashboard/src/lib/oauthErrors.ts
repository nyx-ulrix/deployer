const MESSAGES: Record<string, string> = {
  oauth_failed: "Sign-in with the provider failed. Please try again.",
  oauth_state_invalid: "The sign-in attempt expired or was tampered with. Please start again.",
  account_exists_link_required:
    "An account with this email already exists. Sign in with your password or the provider you used before, then link this one in Settings → Account.",
  identity_in_use: "That provider account is already linked to a different Deployer user.",
  signup_disabled: "Sign-up is disabled on this Deployer instance. Ask the owner for an invite.",
  provider_not_configured: "That sign-in provider isn't configured on this Deployer instance yet.",
  email_not_verified: "Your provider account's email address isn't verified. Verify it with the provider and try again.",
  invalid_credentials: "Wrong email or password.",
  rate_limited: "Too many attempts. Please wait a few minutes and try again.",
  invite_email_mismatch: "This invite is for a different email address. Sign in with the invited account.",
};

export function oauthErrorMessage(code: string | null | undefined): string | null {
  if (!code) return null;
  return MESSAGES[code] ?? `Sign-in failed (${code}).`;
}

export const PROVIDER_LABELS = { google: "Google", github: "GitHub" } as const;
