/** Only allow same-origin relative paths as post-login redirects (mirrors api sanitize_redirect). */
export function safeRedirect(value: string | null | undefined, fallback = "/"): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return fallback;
  // Browsers treat '\' as '/' and strip tabs/newlines, so "/\\evil.com" or "/\t/evil.com" become "//evil.com".
  // eslint-disable-next-line no-control-regex
  if (/[\\\x00-\x1f\x7f]/.test(value)) return fallback;
  return value;
}
