import { describe, expect, it } from "vitest";
import { csvField, exportFilename, rowsToObjects, toCsv } from "./csv";

describe("csvField", () => {
  it("leaves plain values alone and blanks null/missing", () => {
    expect(csvField("abc")).toBe("abc");
    expect(csvField(42)).toBe("42");
    expect(csvField(true)).toBe("true");
    expect(csvField(null)).toBe("");
    expect(csvField(undefined)).toBe("");
  });

  it("quotes commas, quotes and line breaks", () => {
    expect(csvField("a,b")).toBe('"a,b"');
    expect(csvField('say "hi"')).toBe('"say ""hi"""');
    expect(csvField("line1\nline2")).toBe('"line1\nline2"');
    expect(csvField("crlf\r\n")).toBe('"crlf\r\n"');
  });

  it("serialises objects and arrays as JSON", () => {
    expect(csvField({ $base64: "AAEC" })).toBe('"{""$base64"":""AAEC""}"');
    expect(csvField([1, "x"])).toBe('"[1,""x""]"');
  });
});

describe("toCsv", () => {
  it("writes a header, CRLF rows and a trailing newline", () => {
    const csv = toCsv(
      ["id", "email", "note"],
      [
        [1, "a@b.c", null],
        [2, "x,y@z", "said \"no\""],
      ],
    );
    expect(csv).toBe('id,email,note\r\n1,a@b.c,\r\n2,"x,y@z","said ""no"""\r\n');
  });

  it("pads short rows and ignores extra values", () => {
    expect(toCsv(["a", "b"], [[1], [1, 2, 3]])).toBe("a,b\r\n1,\r\n1,2\r\n");
  });
});

describe("rowsToObjects", () => {
  it("keys each row by column", () => {
    expect(rowsToObjects(["id", "name"], [[1, "a"], [2, undefined]])).toEqual([
      { id: 1, name: "a" },
      { id: 2, name: undefined },
    ]);
  });
});

describe("exportFilename", () => {
  it("slugs the base and appends the statement number", () => {
    expect(exportFilename("SELECT * FROM users WHERE id = 1", "csv", 0)).toBe("select-from-users-where-id-1-1.csv");
    expect(exportFilename("events", "json")).toBe("events.json");
    expect(exportFilename("   ", "csv")).toBe("result.csv");
  });

  it("keeps names short", () => {
    const name = exportFilename("x".repeat(200), "csv");
    expect(name.length).toBeLessThanOrEqual(44);
  });
});
