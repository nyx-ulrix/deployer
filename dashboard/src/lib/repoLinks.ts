// Links to docs and the agent skill in the Deployer repository, pinned to the release this dashboard was built
// from (A-197). Release images set VITE_DEPLOYER_REF to the tag (dashboard/Dockerfile, release.yml); a dev or
// from-source build falls back to main.
export function repoLinks(repo = "nyx-ulrix/deployer", ref = "main") {
  return {
    blob: (path: string) => `https://github.com/${repo}/blob/${ref}/${path}`,
    raw: (path: string) => `https://raw.githubusercontent.com/${repo}/${ref}/${path}`,
  };
}

export const { blob: repoBlobUrl, raw: repoRawUrl } = repoLinks(
  import.meta.env.VITE_DEPLOYER_REPO || undefined,
  import.meta.env.VITE_DEPLOYER_REF || undefined,
);
