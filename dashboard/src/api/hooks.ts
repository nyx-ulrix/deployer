import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api, qk } from "./endpoints";
import type { JobStatus } from "./types";

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

/** Tables/collections of one data source (`GET /projects/{id}/schema?source_id=`), e.g. for query completion. */
export function useSourceSchema(projectId: string, sourceId: string | null) {
  return useQuery({
    queryKey: qk.sourceSchema(projectId, sourceId ?? ""),
    queryFn: () => api.schema.get(projectId, { source_id: sourceId ?? undefined }),
    enabled: Boolean(sourceId),
    staleTime: 30_000,
    retry: 1,
    select: (schema) => schema.sources.find((s) => s.source_id === sourceId) ?? null,
  });
}

export function useSavedQueries(projectId: string) {
  return useQuery({ queryKey: qk.savedQueries(projectId), queryFn: () => api.savedQueries.list(projectId) });
}

const QUERY_LOG_PAGE = 50;

/** Newest-first pages of one source's query log; the next page starts before the last row's `created_at`. */
export function useQueryLog(projectId: string, sourceId: string, user: "me" | "all", enabled = true) {
  return useInfiniteQuery({
    queryKey: qk.queryLog(projectId, sourceId, user),
    queryFn: ({ pageParam }) =>
      api.queryLog.list(projectId, { source_id: sourceId, user, limit: QUERY_LOG_PAGE, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => (last.has_more && last.runs.length > 0 ? last.runs[last.runs.length - 1].created_at : undefined),
    enabled,
    staleTime: 10_000,
  });
}

export function useInstanceSettings(enabled = true) {
  return useQuery({ queryKey: qk.instanceSettings, queryFn: api.instance.settings, enabled });
}

export function useDevices(scope: "mine" | "all" = "mine", enabled = true) {
  return useQuery({
    queryKey: qk.devices(scope),
    queryFn: () => api.devices.list(scope),
    enabled,
    refetchInterval: 30_000,
  });
}

export function usePlacementOptions(projectId: string, enabled = true) {
  return useQuery({
    queryKey: qk.placement(projectId),
    queryFn: () => api.dataSources.placementOptions(projectId),
    enabled,
    staleTime: 10_000,
  });
}

const JOB_POLL_MS = 1500;

export function isJobFinished(status: JobStatus | undefined): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}

/** Poll a job every 1.5 s until it finishes. */
export function useJob(projectId: string, jobId: string | null) {
  return useQuery({
    queryKey: qk.job(projectId, jobId ?? ""),
    queryFn: () => api.jobs.get(projectId, jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (isJobFinished(query.state.data?.status) ? false : JOB_POLL_MS),
    staleTime: 0,
  });
}
