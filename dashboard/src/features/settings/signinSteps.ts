import type { ProviderName } from "../../api/types";
import type { StepStatus } from "../../components/ui/StepCard";

export const GITHUB_STEP_TITLES = ["Create the OAuth app", "Generate a client secret", "Paste them here"] as const;

// Google has no public API to create OAuth web clients, so this is a guide, not automation.
export const GOOGLE_STEP_TITLES = [
  "Create or pick a Google Cloud project",
  "Fill in the Branding page",
  "Choose who can sign in",
  "Create a Web application client",
  "Copy the Client ID and secret",
  "Paste them here",
] as const;

const trim = (url: string) => url.trim().replace(/\/+$/, "");

export function isLocalUrl(url: string): boolean {
  return /^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(\/|$)/i.test(url.trim());
}

export function callbackUrl(provider: ProviderName, baseUrl: string): string {
  return `${trim(baseUrl)}/v1/auth/oauth/${provider}/callback`;
}

/**
 * Callback URLs to register: the public one first, plus the Deployer PC's own address (`local_url` from the API,
 * with its real port) when it differs, so sign-in on that PC keeps working.
 */
export function callbackUrls(provider: ProviderName, publicUrl: string, localUrl: string): string[] {
  const urls = [callbackUrl(provider, publicUrl), callbackUrl(provider, localUrl)];
  return urls[0].toLowerCase() === urls[1].toLowerCase() ? [urls[0]] : urls;
}

/**
 * GitHub's "Register a new OAuth app" form, pre-filled. The query names are the form's own field names
 * (`oauth_application[...]`); GitHub doesn't document them, so the guide also shows copy fields for each value.
 */
export function githubPrefillUrl(publicUrl: string): string {
  const params = new URLSearchParams({
    "oauth_application[name]": "Deployer",
    "oauth_application[url]": trim(publicUrl),
    "oauth_application[callback_url]": callbackUrl("github", publicUrl),
  });
  return `https://github.com/settings/applications/new?${params.toString()}`;
}

/**
 * Step status for a sign-in guide. The console steps happen outside Deployer, so they count as done once the user
 * says so (`acknowledged`, 0-based indexes) or once a Client ID is saved; the last step (paste) is done when configured.
 */
export function deriveSigninSteps(
  count: number,
  s: { configured: boolean; clientIdSaved: boolean; acknowledged: readonly number[] },
): StepStatus[] {
  const done = Array.from(
    { length: count },
    (_, i) => s.configured || (i < count - 1 && (s.clientIdSaved || s.acknowledged.includes(i))),
  );
  const current = done.indexOf(false);
  return done.map((d, i) => (d ? "done" : i === current ? "current" : "todo"));
}

// Mirrors validate_oauth_value in api/app/services/instance_settings.py for instant feedback; the API still decides.
const GOOGLE_ID = /^\d+-[a-z0-9]+\.apps\.googleusercontent\.com$/;
const GITHUB_ID = /^((Ov23|Iv1\.|Iv23)[A-Za-z0-9._-]+|[A-Za-z0-9]{20})$/;
const LABEL = /^(client[ _-]?)?(id|secret)[\s:=]/i;
const EXAMPLES = {
  google: { id: "1234-abc.apps.googleusercontent.com", secret: "GOCSPX-..." },
  github: { id: "Ov23li...", secret: "a 40-character hex string" },
} as const;

/** What's wrong with a pasted Client ID / secret, or null if it looks fine (or is empty). */
export function oauthValueError(provider: ProviderName, part: "id" | "secret", raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  const name = `${provider === "google" ? "Google" : "GitHub"} ${part === "id" ? "Client ID" : "Client secret"}`;
  const example = EXAMPLES[provider][part];
  if (LABEL.test(value) || /\s/.test(value))
    return `Paste only the ${name}, e.g. ${example} — not the whole block (the value has spaces or an ID/SECRET label in it).`;
  if (part === "secret") {
    return GOOGLE_ID.test(value) || value.endsWith(".googleusercontent.com") || GITHUB_ID.test(value)
      ? `That looks like the Client ID, not the ${name} — paste the secret, e.g. ${example}.`
      : null;
  }
  if ((provider === "google" ? GOOGLE_ID : GITHUB_ID).test(value)) return null;
  const hint = value.startsWith("GOCSPX-") ? " (that looks like the Client secret)" : "";
  return `That is not a ${name}${hint} — paste only the Client ID, e.g. ${example}.`;
}
