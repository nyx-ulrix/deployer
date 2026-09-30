import { describe, expect, it } from "vitest";
import { docIdString } from "./json";

describe("docIdString", () => {
  it("unwraps Extended JSON ids and stringifies the rest", () => {
    expect(docIdString({ $oid: "65f0c0ffee" })).toBe("65f0c0ffee");
    expect(docIdString({ $uuid: "0b1c-uuid" })).toBe("0b1c-uuid");
    expect(docIdString({ k: 1 })).toBe('{"k":1}');
    expect(docIdString(7)).toBe("7");
    expect(docIdString("abc")).toBe("abc");
    expect(docIdString(null)).toBeNull();
    expect(docIdString(undefined)).toBeNull();
  });
});
