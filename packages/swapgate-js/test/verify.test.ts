import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { buildCompareArgs, canonicalize, contentHash, summarize, verifyReceipt, type SwapReceipt } from "../src/index.js";

const KEY = "swapgate-interop-test-key";

function signedGolden(): SwapReceipt {
  return JSON.parse(readFileSync(new URL("../../../tests/golden/signed-receipt.json", import.meta.url), "utf8"));
}

describe("receipt interop (Python-signed golden)", () => {
  it("recomputes the same content hash (canonical JSON compatible)", () => {
    const receipt = signedGolden();
    expect(contentHash(receipt)).toBe(receipt.content_hash);
  });

  it("verifies the Python-signed receipt", () => {
    expect(verifyReceipt(signedGolden(), KEY)).toBe(true);
  });

  it("rejects tampered receipts", () => {
    const receipt = signedGolden();
    receipt.summary.passed = !receipt.summary.passed;
    expect(verifyReceipt(receipt, KEY)).toBe(false);
  });

  it("rejects the wrong key", () => {
    expect(verifyReceipt(signedGolden(), "wrong-key")).toBe(false);
  });

  it("summarizes", () => {
    expect(summarize(signedGolden())).toContain("-> PASS");
  });
});

describe("canonicalize", () => {
  it("sorts keys and strips volatile fields", () => {
    expect(canonicalize({ b: 1, a: [2, { d: 4, c: 3 }], content_hash: "x" })).toBe('{"a":[2,{"c":3,"d":4}],"b":1}');
  });
});

describe("buildCompareArgs", () => {
  it("builds compare argv", () => {
    expect(buildCompareArgs({ suite: "s.json", candidate: "mock:regress", failUnder: 0.5 })).toEqual([
      "compare", "--suite", "s.json", "--baseline", "mock:parity",
      "--candidate", "mock:regress", "--judge", "deterministic", "--fail-under", "0.5",
    ]);
  });
});
