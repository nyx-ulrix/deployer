import { useQuery } from "@tanstack/react-query";
import { api, qk } from "./endpoints";

export function useSetupStatus() {
  return useQuery({ queryKey: qk.setupStatus, queryFn: api.setup.status, staleTime: 60_000, retry: 1 });
}

export function useProviders() {
  return useQuery({ queryKey: qk.providers, queryFn: api.auth.providers, staleTime: 60_000 });
}

export function useProjects() {
  return useQuery({ queryKey: qk.projects, queryFn: api.projects.list });
}

export function useProject(projectId: string) {
  return useQuery({ queryKey: qk.project(projectId), queryFn: () => api.projects.get(projectId) });
}

export function useDataSources(projectId: string) {
  return useQuery({ queryKey: qk.dataSources(projectId), queryFn: () => api.dataSources.list(projectId) });
}

export function useSchema(projectId: string, enabled = true) {
  return useQuery({
    queryKey: qk.schema(projectId),
    queryFn: () => api.schema.get(projectId),
    enabled,
    staleTime: 30_000,
  });
}

export function useInstanceSettings(enabled = true) {
  return useQuery({ queryKey: qk.instanceSettings, queryFn: api.instance.settings, enabled });
}
