import { describe, expect, it } from "vitest";
import { jobLabel } from "./jobs";

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
