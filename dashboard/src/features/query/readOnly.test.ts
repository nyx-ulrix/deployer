import { describe, expect, it } from "vitest";
import { checkMongoReadOnly, checkReadOnly, checkSqlReadOnly, firstKeyword, splitSqlStatements } from "./readOnly";

describe("splitSqlStatements", () => {
  it("splits on semicolons and drops blanks", () => {
    expect(splitSqlStatements("SELECT 1; SELECT 2;;  ")).toEqual(["SELECT 1", "SELECT 2"]);
    expect(splitSqlStatements("")).toEqual([]);
  });

  it("ignores semicolons inside strings and comments", () => {
    expect(splitSqlStatements("SELECT 'a;b', \"c;d\", `e;f` FROM t; -- trailing; comment\nSELECT 2")).toEqual([
      "SELECT 'a;b', \"c;d\", `e;f` FROM t",
      "SELECT 2",
    ]);
    expect(splitSqlStatements("/* DROP TABLE x; */ SELECT 1 # DELETE; \n; SELECT 'it''s; fine'")).toEqual([
      "SELECT 1",
      "SELECT 'it''s; fine'",
    ]);
    expect(splitSqlStatements("SELECT 'back\\'slash;' ; SELECT 3")).toEqual(["SELECT 'back\\'slash;'", "SELECT 3"]);
  });

  it("survives an unterminated string or comment", () => {
    expect(splitSqlStatements("SELECT 'open; SELECT 2")).toEqual(["SELECT 'open; SELECT 2"]);
    expect(splitSqlStatements("SELECT 1 /* never closed; DROP")).toEqual(["SELECT 1"]);
  });
});

describe("firstKeyword", () => {
  it("returns the lower-cased first word", () => {
    expect(firstKeyword("  Select *")).toBe("select");
    expect(firstKeyword("(SELECT 1)")).toBe("");
    expect(firstKeyword("")).toBe("");
  });
});

describe("checkSqlReadOnly", () => {
  it("accepts read-only statements, also after comments", () => {
    for (const q of [
      "SELECT * FROM users",
      "-- note\nselect 1; show tables; EXPLAIN SELECT 1",
      "WITH x AS (SELECT 1) SELECT * FROM x",
      "DESCRIBE users; DESC users; TABLE users; VALUES (1)",
      "/* DELETE FROM t */ SELECT 1",
      "",
    ]) {
      expect(checkSqlReadOnly(q)).toEqual({ readOnly: true });
    }
  });

  it("flags the first non read-only statement", () => {
    expect(checkSqlReadOnly("SELECT 1; DELETE FROM users")).toEqual({
      readOnly: false,
      reason: "A statement starting with “DELETE” isn't read-only.",
    });
    expect(checkSqlReadOnly("update t set a = 1").readOnly).toBe(false);
    expect(checkSqlReadOnly("INSERT INTO t VALUES (1)").readOnly).toBe(false);
    expect(checkSqlReadOnly("(SELECT 1)").readOnly).toBe(false);
  });

  it("is not fooled by write keywords inside strings", () => {
    expect(checkSqlReadOnly("SELECT 'DROP TABLE users' AS t").readOnly).toBe(true);
  });
});

describe("checkMongoReadOnly", () => {
  it("accepts reads", () => {
    expect(checkMongoReadOnly('db.users.find({ status: "active" }).limit(20)')).toEqual({ readOnly: true });
    expect(checkMongoReadOnly("db.orders.aggregate([{ $group: { _id: '$status', n: { $sum: 1 } } }])").readOnly).toBe(true);
    expect(checkMongoReadOnly("db.users.countDocuments()").readOnly).toBe(true);
  });

  it("flags every write or restricted name as a whole word", () => {
    expect(checkMongoReadOnly("db.users.insertOne({})")).toEqual({
      readOnly: false,
      reason: "“insertOne” is a write or restricted method.",
    });
    for (const code of [
      "db.users.deleteMany({})",
      "db.users.drop()",
      "db.getSiblingDB('admin').stats()",
      "load('x.js')",
      "process.env",
      "const fs = 1",
      "db.runCommand({ ping: 1 })",
      "db.t.findOneAndUpdate({}, {})",
    ]) {
      expect(checkMongoReadOnly(code).readOnly).toBe(false);
    }
  });

  it("does not match names that merely contain a restricted word", () => {
    expect(checkMongoReadOnly("db.updates.find()").readOnly).toBe(true);
    expect(checkMongoReadOnly("db.t.find({ processed: true })").readOnly).toBe(true);
    expect(checkMongoReadOnly("db.t.find({ $fs: 1 })").readOnly).toBe(true);
  });
});

describe("checkReadOnly", () => {
  it("dispatches on the source kind", () => {
    expect(checkReadOnly("sql", "DROP TABLE x").readOnly).toBe(false);
    expect(checkReadOnly("nosql", "DROP TABLE x").readOnly).toBe(true);
    expect(checkReadOnly("nosql", "db.x.remove({})").readOnly).toBe(false);
  });
});
