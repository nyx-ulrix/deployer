import { useOutletContext } from "react-router-dom";
import type { Project, Role } from "../../api/types";
import { hasRole } from "../../lib/roles";

export type ProjectOutletContext = { project: Project };

export function useProjectContext() {
  const { project } = useOutletContext<ProjectOutletContext>();
  const can = (role: Role) => hasRole(project.my_role, role);
  return { project, can };
}
