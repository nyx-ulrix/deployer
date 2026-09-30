import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";

/** A link to an outside site: opens in a new tab with the external-link icon. */
export function ExtLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="inline-flex items-center gap-0.5 font-medium text-accent hover:underline"
    >
      {children}
      <ExternalLink className="size-3" />
    </a>
  );
}
