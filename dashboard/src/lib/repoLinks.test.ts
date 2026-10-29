import { describe, expect, it } from "vitest";
import { repoLinks } from "./repoLinks";

describe("repoLinks", () => {
  it("pins links to the build's release tag and repository", () => {
    const l = repoLinks("someone/fork", "v1.2.3");
    expect(l.blob("docs/MCP.md")).toBe("https://github.com/someone/fork/blob/v1.2.3/docs/MCP.md");
    expect(l.raw("installer/install.sh")).toBe(
      "https://raw.githubusercontent.com/someone/fork/v1.2.3/installer/install.sh",
    );
  });

  it("falls back to the upstream main branch for dev builds", () => {
    expect(repoLinks().blob("docs/DATA_API.md")).toBe("https://github.com/nyx-ulrix/deployer/blob/main/docs/DATA_API.md");
  });
});
