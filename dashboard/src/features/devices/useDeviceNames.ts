import { useQuery } from "@tanstack/react-query";
import { api, qk } from "../../api/endpoints";
import type { DataSource } from "../../api/types";

/**
 * Names of host devices for a project's data sources. Uses `device_name` from the source when the API
 * provides it, otherwise the project's placement options (admin-only APIs fail quietly).
 */
export function useDeviceNames(projectId: string, enabled: boolean) {
  const options = useQuery({
    queryKey: qk.placement(projectId),
    queryFn: () => api.dataSources.placementOptions(projectId),
    enabled,
    retry: false,
    staleTime: 60_000,
  });
  return (source: Pick<DataSource, "device_id" | "device_name">): string | null => {
    if (!source.device_id) return null;
    return (
      source.device_name ?? options.data?.find((o) => o.device_id === source.device_id)?.name ?? "a host device"
    );
  };
}
