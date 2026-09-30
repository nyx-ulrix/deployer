import { describe, expect, it } from "vitest";
import type { Field } from "../../api/types";
import { fromText, toText } from "./rowValues";

const col = (data_type: string) => ({ name: "c", data_type, nullable: true }) as unknown as Field;

describe("fromText", () => {
  it("keeps a bigint past 2^53 as text so no digits are lost", () => {
    expect(fromText("9007199254740993", col("bigint"), "9007199254740993")).toBe("9007199254740993");
    expect(fromText("42", col("bigint"), 1)).toBe(42);
    expect(fromText("-1.5e3", col("double"), undefined)).toBe(-1500);
    expect(fromText("12abc", col("int"), 1)).toBe("12abc");
  });

  it("reads yes/no columns as booleans", () => {
    expect(fromText("1", col("tinyint(1)"), 0)).toBe(true);
    expect(fromText("FALSE", col("boolean"), undefined)).toBe(false);
    expect(fromText("true", undefined, false)).toBe(true);
    // tinyint(4) is a number, not a flag.
    expect(fromText("1", col("tinyint(4)"), 3)).toBe(1);
  });

  it("parses JSON back when the original was an object, else keeps the text", () => {
    expect(fromText('{"a":[1,2]}', col("json"), { a: [] })).toEqual({ a: [1, 2] });
    expect(fromText("{broken", col("json"), { a: 1 })).toBe("{broken");
    expect(fromText('{"a":1}', col("varchar(255)"), "x")).toBe('{"a":1}');
  });

  it("round-trips through toText", () => {
    expect(toText(null)).toBe("");
    expect(toText({ a: 1 })).toBe('{"a":1}');
    expect(fromText(toText(7), col("int"), 7)).toBe(7);
  });
});
