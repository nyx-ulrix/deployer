/// <reference types="node" />
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { MIN_PASSPHRASE, MIN_PASSWORD } from "./constants";

const serverValue = (file: string, name: string) => {
  const source = readFileSync(
    join(
      dirname(fileURLToPath(import.meta.url)),
      "../../../api/app/services",
      file,
    ),
    "utf8",
  );
  return Number(source.match(new RegExp(`^${name} = ([0-9]+)`, "m"))?.[1]);
};

describe("form minimums match the server", () => {
  it("password length", () => {
    expect(MIN_PASSWORD).toBe(
      serverValue("passwords.py", "MIN_PASSWORD_LENGTH"),
    );
  });

  it("transfer passphrase length", () => {
    expect(MIN_PASSPHRASE).toBe(serverValue("transfer.py", "MIN_PASSPHRASE"));
  });
});
