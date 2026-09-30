import { describe, expect, it } from "vitest";
import { JOB_STATUS, jobLabel } from "./jobs";

describe("jobLabel", () => {
  it("names the types the regex labels got wrong", () => {
    expect(jobLabel("source.undelete")).toBe("Restore deleted database");
    expect(jobLabel("source.finalize_delete")).toBe("Delete database");
    expect(jobLabel("app.replicate")).toBe("Deploy app to device");
    expect(jobLabel("app.deploy")).toBe("Deploy app");
  });

  it("falls back to a neutral label instead of an internal id", () => {
    expect(jobLabel("something.new")).toBe("Background task");
  });
});

describe("JOB_STATUS", () => {
  it("labels every status", () => {
    for (const s of ["queued", "running", "succeeded", "failed", "cancelled"] as const) {
      expect(JOB_STATUS[s].label).toBeTruthy();
    }
    expect(JOB_STATUS.failed.tone).toBe("danger");
  });
});
