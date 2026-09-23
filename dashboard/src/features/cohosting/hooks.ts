import { useQuery } from "@tanstack/react-query";
import { api, qk } from "../../api/endpoints";
import type { DataSource } from "../../api/types";
import { useCurrentUser } from "../../auth/auth-context";
import { useProjectContext } from "../projects/project-context";
import { canManageReplica } from "./cohosting";

/** Display names of project members, for "resolved by" and history rows. */
export function useMemberNames(projectId: string) {
  const members = useQuery({ queryKey: qk.members(projectId), queryFn: () => api.members.list(projectId), staleTime: 60_000 });
  return (userId: string | null): string => {
    if (!userId) return "sync";
    const m = members.data?.find((x) => x.user_id === userId);
    return m ? m.display_name || m.email : "a former member";
  };
}

/** Who may resolve / restore rows of a copy: its co-host or a project admin (same rule as the API). */
export function useCanManage(source: DataSource) {
  const { can } = useProjectContext();
  const me = useCurrentUser();
  return (replicaId: string) => {
    const r = source.replicas?.find((x) => x.id === replicaId);
    return canManageReplica({ owner_id: r?.owner_id ?? null }, me.id, can("admin"));
  };
}
