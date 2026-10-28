/** SwapGate SDK: receipt types + offline verification (no dependencies). */
import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export interface Verdict {
  passed: boolean;
  score: number;
  label: string;
  probability: number;
  rationale: string;
}

export interface CaseComparison {
  case_id: string;
  baseline_output: string;
  baseline_verdict: Verdict;
  candidate_output: string;
  candidate_verdict: Verdict;
  regressed: boolean;
}

export interface ReceiptSummary {
  suite: string;
  suite_version: string;
  baseline: string;
  candidate: string;
  judge: string;
  n_cases: number;
  baseline_pass_rate: number;
  candidate_pass_rate: number;
  regression_gap: number;
  fail_under: number;
  max_regression: number;
  passed: boolean;
  regressed_case_ids: string[];
}

export interface SwapReceipt {
  v: number;
  issued_at: string;
  summary: ReceiptSummary;
  cases: CaseComparison[];
  content_hash: string;
  signature: string;
  signature_scheme: string;
}

const VOLATILE = new Set(["content_hash", "signature", "signature_scheme"]);

/** Canonical JSON: sorted keys, compact separators — byte-compatible with Python. */
export function canonicalize(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value) ?? "null";
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(",")}]`;
  }
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([k]) => !VOLATILE.has(k))
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalize(v)}`).join(",")}}`;
}

export function contentHash(receipt: SwapReceipt): string {
  return createHash("sha256").update(canonicalize(receipt), "utf8").digest("hex");
}

/** Verify a signed receipt. `key` is the raw key bytes (utf-8 of the key file). */
export function verifyReceipt(receipt: SwapReceipt, key: string | Buffer): boolean {
  if (receipt.signature_scheme !== "hmac-sha256-v1") return false;
  if (contentHash(receipt) !== receipt.content_hash) return false;
  const expected = createHmac("sha256", key).update(receipt.content_hash, "utf8").digest();
  const actual = Buffer.from(receipt.signature, "hex");
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

export function summarize(receipt: SwapReceipt): string {
  const s = receipt.summary;
  return (
    `suite ${s.suite} v${s.suite_version}: baseline ${s.baseline} ` +
    `${s.baseline_pass_rate} vs candidate ${s.candidate} ${s.candidate_pass_rate} ` +
    `(gap ${s.regression_gap}) -> ${s.passed ? "PASS" : "FAIL"}`
  );
}

/** Build `swapgate compare` argv from options (for spawning the CLI). */
export function buildCompareArgs(options: {
  suite: string;
  baseline?: string;
  candidate?: string;
  judge?: string;
  failUnder?: number;
  maxRegression?: number;
  out?: string;
}): string[] {
  const o = { baseline: "mock:parity", candidate: "mock:parity", judge: "deterministic", ...options };
  const argv = ["compare", "--suite", o.suite, "--baseline", o.baseline, "--candidate", o.candidate, "--judge", o.judge];
  if (o.failUnder !== undefined) argv.push("--fail-under", String(o.failUnder));
  if (o.maxRegression !== undefined) argv.push("--max-regression", String(o.maxRegression));
  if (o.out !== undefined) argv.push("--out", o.out);
  return argv;
}
