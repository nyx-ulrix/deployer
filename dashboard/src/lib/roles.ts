import type { Role } from "../api/types";

const ORDER: Record<Role, number> = { viewer: 0, developer: 1, admin: 2, owner: 3 };

/** True when `role` is at least `required` (viewer < developer < admin < owner). */
export function hasRole(role: Role | undefined | null, required: Role): boolean {
  if (!role) return false;
  return ORDER[role] >= ORDER[required];
}

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  developer: "Developer",
  viewer: "Viewer",
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  owner: "Full control, including deleting the project and dropping data.",
  admin: "Manage members, invites, API keys and data sources.",
  developer: "Change schema and data, view connection details.",
  viewer: "Read-only access to schema and data.",
};
