# swapgate

SwapGate SDK for Node: swap-receipt types and offline verification. Zero
runtime dependencies.

## Install

```sh
npm install swapgate
```

## Verify a receipt

```js
import { readFileSync } from "node:fs";
import { verifyReceipt, summarize } from "swapgate";

const receipt = JSON.parse(readFileSync("receipt.json", "utf8"));
const key = readFileSync(process.env.SWAPGATE_KEY_FILE, "utf8"); // raw key bytes
if (verifyReceipt(receipt, key)) {
  console.log(summarize(receipt));
} else {
  console.error("receipt INVALID");
  process.exit(1);
}
```

## API

- `verifyReceipt(receipt, key)` — check the content hash and HMAC-SHA256
  signature (`hmac-sha256-v1` only; unsigned receipts return `false`).
- `contentHash(receipt)` / `canonicalize(value)` — canonical JSON
  (sorted keys, short numbers) matching the Python implementation.
- `summarize(receipt)` — one-line `suite … -> PASS|FAIL` verdict.
- `buildCompareArgs(options)` — build `swapgate compare` argv for spawning
  the CLI (`{suite, baseline?, candidate?, judge?, failUnder?,
  maxRegression?, out?}`).

Types: `SwapReceipt`, `ReceiptSummary`, `CaseComparison`, `Verdict`.

## Links

- CLI + docs: <https://github.com/nitishagar/swapgate>
- Guide: <https://nitishagar.github.io/swapgate/>

Apache-2.0.
