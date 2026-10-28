# SwapGate completeness — Implementation + Test Validation

Small-scale merge: one artifact covers both the implementation checklist
(items 1–8) and the test checklist (items 9–13). Adversarial posture: each
item defaulted to FAIL until the diff earned PASS with file:line evidence.

Scope: `git diff 1cd9cf9..HEAD` (53 files) + PLAN.md (rev 3, incl. Amendments)
+ IMPLICIT_SPEC.md. Corroboration runs: full suite `152 passed, 1 skipped`
in `.venv` (skip = pre-existing `SWAPGATE_LIVE` gate), billing/e2e/diet
files genuinely execute (9 passed), hosted receipt cross-checked with the TS
SDK (`TS verify ok`), malformed-input probe against a live server.

## Item verdicts

| # | Item | Verdict |
|---|---|---|
| 1 | Plan conformance | FAIL (I1–I5, I8) |
| 2 | Spec invariants | FAIL (I2 mechanism only; all else hold) |
| 3 | Failure/concurrency | PASS |
| 4 | Cost-model conformance | PASS |
| 5 | Anti-pattern sweep | FAIL (nit-severity only) |
| 6 | Test integrity | PASS |
| 7 | Common defects | FAIL (I6) |
| 8 | Convention fit | PASS |
| 9 | Invariant coverage | FAIL (named gaps below) |
| 10 | Criteria coverage | FAIL (named gaps below) |
| 11 | Real assertions | PASS |
| 12 | Over-mocking | PASS |
| 13 | Determinism | PASS |

## Amendments (item 1 sub-check)

- AM1 (P1, factual) — PASS. Code uses `mock_response=ValueError(...)`
  (`tests/e2e/litellm_harness.py:77`); installed litellm is 1.106.5, exactly
  the cited version; e2e failure capture green corroborates the mechanism.
  Test-only, no interface change; factual label stands.
- AM2 (P2, factual) — PASS. `tests/e2e/test_rubrics_llm_e2e.py` exists at the
  amended name; duplicate-basename rationale is valid pytest behavior.
- AM3 (P3, factual) — PASS with nit N1. `judges.get_judge`
  (`src/swapgate/judges/__init__.py:22`) holds the identical mapping and
  `cli._judge_for` (`src/swapgate/cli.py:101`) delegates; `schedule.py:19`
  imports the factory. Internal refactor, no user-visible interface change,
  so the factual label stands. But the stated reason is inaccurate: no import
  cycle would have occurred (`cli.py:208` imports `schedule` lazily inside
  the command function); the real reasons are private-API reuse and the
  `argparse.Namespace` signature mismatch. Trivial side effect: unknown-judge
  stderr gained an `error: ` prefix (exit code still 1).

## Important findings

- I1 — serve default key path contradicts the plan.
  PLAN P4: default `~/.swapgate/host-key`. Code: `args.key or
  DEFAULT_KEY_PATH` (`src/swapgate/cli.py:169`) with `DEFAULT_KEY_PATH =
  ~/.swapgate/key` (`src/swapgate/receipt.py:18`); `host-key` appears nowhere
  in src/tests/docs/CI. Unrecorded divergence. Side effect: the server shares
  the CLI `--sign` key instead of the planned separate host key.
- I2 — startup live-credential scan unimplemented; spec mechanism violated.
  PLAN P4: "Startup scans all billing config for live patterns and refuses
  to serve webhooks (exit 1)". SPEC: "Billing refuses to initialize if any
  configured credential matches live patterns". Code checks per-request and
  returns 500 (`src/swapgate/serve.py:213-216`, `236-241`); `cmd_serve`,
  `create_server`, `serve_forever` do no scan, so the server initializes and
  serves `/v1/compare` with live-shaped secrets configured. Containment
  *outcome* still holds (no live webhook is ever recorded), but the
  specified mechanism does not. `docs/hosting.html:67` repeats the false
  claim ("refuses to start"). Unrecorded; no test covers startup refusal.
- I3 — SIGTERM exit-0 shutdown unimplemented and untested. PLAN P4: "exit 0
  clean SIGTERM/SIGINT shutdown". No `signal` handling exists in `serve.py`
  or `cli.py`; SIGTERM kills with 143 (SIGINT → 0 via `cli.py:178` works).
  No shutdown test exists.
- I4 — scheduled-selftest diverges from plan letter (code is right, plan is
  wrong, no amendment). PLAN P3: "`--force` twice (second run: nothing
  due, exit 0)" — self-contradictory, since `--force` ignores due-state.
  CI correctly runs `--force` then without (`.github/workflows/ci.yml:174-175`,
  matching the P3 E2E criterion). Needs a one-line amendment.
- I5 — P6 `PAGES` instruction not followed (plan is wrong, no amendment).
  PLAN P6: "`PAGES` gains `docs/reports/001-open-weights.html`".
  `tests/test_docs.py:9` gains only `hosting.html`; only `test_report_indexed`
  covers the report page. The plan letter is unworkable (`DOCS/"docs/reports/..."`
  mis-joins and the fragment-style page would fail title/nav tests), so the
  code's direction is defensible — but unrecorded, and the report page now
  escapes the external-asset/title/home checks. Needs an amendment.
- I6 — malformed hosted inputs drop the connection instead of returning the
  contracted JSON error. `POST /v1/compare` with `baseline`/`candidate: null`
  raises `AttributeError` in `parse_provider` (`src/swapgate/serve.py:140-141`,
  only `ValueError` caught); with `metadata: "x"` raises `ValueError` in
  `EvalSuite.from_dict` (`src/swapgate/serve.py:126`, only
  `TypeError`/`KeyError` caught). Both escape `_dispatch` (catches only
  `ApiError`/`BrokenPipeError`) and the server closes without a response —
  verified empirically (`RemoteDisconnected` on all three; null/int `judge`
  correctly return 400). Violates "Errors: `{error:{code,message}}`".
  Same root cause aborts a scheduler tick with a traceback (`AttributeError`
  uncaught by `cli.main`). Fix: widen the two `except` clauses (+ null-guard
  providers); add tests.
- I7 — plan-explicit behaviors with no test: (a) serve config-error exit 1
  (bad `--port`; plan says bind-failure/config-error "both tested" — only
  the port-conflict half exists, `tests/test_serve.py` has 8 tests, none for
  bad port); (b) hosted gate-fail → 200 with `passed:false`; (c) claim
  release after a `run_entry` error (no post-error re-claim assertion;
  primitive release is covered in `tests/test_history.py`, the `finally` in
  `src/swapgate/schedule.py:134` is not exercised on the error path).
- I8 — plan-explicit doc content missing: report has no "documented
  live-provider commands" (`examples/swap-reports/001-open-weights.md`
  verified by grep; "no live claims" honored) and key rotation
  ("replace + restart") is nowhere in `docs/hosting.html` (grep confirms).

## Spec invariants spot-check (item 2)

Hold with line evidence: exit codes (`cli.py:216-217`, `183-192`,
`163-180`); gate rule + goldens untouched in diff; canonical/HMAC via
untouched `receipt.py` + TS cross-check corroborated by probe; unsigned
shapes pinned (`test_cli.py`, `test_mcp.py`); approval stamps both paths
(`cli.py:69`, `evals.py:144`) with scheduler/hosted refusal
(`schedule.py:72-77`, `serve.py:129-130`); capture/parser behavior untouched
+ parser-raise pin; diet guard green (`test_diet.py`, lazy SDK imports only
in `billing.py:28,36`); receipt-identity modulo `VOLATILE`
(`test_schedule.py`); append-only runs (INSERT-only); team scoping + NULL
never served (`serve.py:173-196`); webhook idempotency (`billing.py:42-62`,
duplicate→200); 401/404 indistinguishability (`serve.py:74-82,173-181`).
Single failure: I2 (refuses-to-initialize mechanism).

## Failure/concurrency (item 3, PASS) and cost (item 4, PASS)

Claims released on every path via `try/finally` (`schedule.py:123-135`);
`_connect` rolls back on exception (`history.py:49-61`); `claim()` uses one
`BEGIN IMMEDIATE` txn with rollback (`history.py:130-157`); webhook
insert+mark is a single txn (crash → rollback → clean retry);
`litellm.callbacks` restored in `finally` (`litellm_harness.py:93-94`);
atomic schedules rewrite (`schedule.py:44-48`). No state leak found on any
error path. No unbudgeted cost: no N+1, no per-row round-trips; full-table
`list_runs` scans serve the plan-specified unpaginated routes at
single-instance scale.

## Test integrity (item 6, PASS)

`tests/test_runner.py`, `tests/test_cli.py`, `tests/test_mcp.py`,
`tests/test_report.py` diffs are purely additive (verified hunk-by-hunk);
the 4 P7 pins are new standalone tests (runner +1, cli +2, mcp +1);
`tests/test_docs.py` `PAGES` edit is plan-mandated. No existing test
edited, deleted, skipped, xfailed, or loosened.

## Coverage gaps (items 9–10)

Beyond I7: null-provider / non-dict-metadata inputs (I6) untested; NaN
threshold literal untested (same line as Inf — nit); Razorpay non-UTF8 body,
empty allowlist, and bad `Content-Length` paths untested (same-line
adjacent — nits). All Local/E2E criteria are otherwise backed: e2e harness,
rubrics, scheduler identity/refusal/single-flight, route matrix, webhook
vectors, contract conformance + round-trip, manifest drift, report indexing,
pins. Oracles genuine: goldens clean (no `tests/golden/` churn, working
tree clean after run), TS interop re-verified by probe, fixtures + mock
providers (no hand-typed verdicts). No tautologies, no subject-mocking.

## Nits (5 of ~12; rest: style/edge trivia)

- N1 — AM3 rationale cites a circular import that cannot occur (lazy
  `cli.py:208`); behavior identical, keep the change.
- N2 — `serve.py` imports `billing` lazily inside handlers
  (`serve.py:208,231`) vs plan's top-level import; safe direction, needs a
  one-line amendment.
- N3 — `DEFAULT_SCHEDULES_PATH` (`schedule.py:23`) is defined but no caller
  uses it (parser inlines the default).
- N4 — diet-guard regex misses multi-imports (`import a, b`) and dynamic
  imports; adequate for the current tree, evadable in principle.
- N5 — `record_event`'s return value (`billing.py:42`) is ignored by both
  callers. (+7 more trivial: NaN/non-UTF8/empty-allowlist assertions,
  skip-path `last_run` assertion, try/except instead of `pytest.raises` in
  `test_billing.py`, private `WebhookSignature._compute_signature` in tests,
  benign schedules-file lost-update under concurrent multi-entry ticks,
  missing trailing newline in selftest suite.)

## Fixes required for PASS

Code: I1 (default to `~/.swapgate/host-key`), I2 (startup scan + exit 1, or
spec/plan amendment + doc fix), I3 (SIGTERM handler or amend the claim), I6
(widen `except` clauses), I8 (two doc sentences). Tests: I7 (three tests).
Plan amendments: I4, I5 (plan wrong, code right), N2, AM3 rationale (N1).

VERDICT: MINOR-FAIL

## Re-verification (author note — resume unavailable, author verified in-place)

The resumed reviewer returned without file/shell tools and could not confirm;
per workflow the author re-verified every item against commit `d5a5393`:

- I1 ✓: fresh-`HOME` probe creates `~/.swapgate/host-key` (empirical).
- I2 ✓: `STRIPE_WEBHOOK_SECRET=sk_live_probe … serve` → `error: …` exit 1,
  no db/key files (empirical + `test_serve_startup_scan_refuses_live_secrets`).
- I3 ✓: `test_serve_sigterm_exits_zero` passes (POSIX subprocess, returncode 0).
- I4/I5/N2/AM3 ✓: 5 factual amendments appended to PLAN.md (8 `AMENDED` lines
  total); I5 evidence re-grepped (report page: 0 home links).
- I6 ✓: null → 400 JSON tests pass; scheduler NULL-skip root-caused to the
  NOT NULL claim INSERT (`claim()` returned False empirically) and fixed with
  pre-claim validation (`test_null_provider_is_error_not_crash`).
- I7 ✓: `test_serve_bad_port_exits_1`, `test_compare_gate_fail_is_200_with_receipt`,
  `test_claim_released_after_entry_error` all pass.
- I8 ✓: rotation paragraph + report live-commands block grepped in place.
- N3 ✓: parser uses `DEFAULT_SCHEDULES_PATH` (`cli.py:232,286`).
- Test integrity ✓: `git diff af4651f..HEAD -- tests/` has zero removed lines.
- Gates: `160 passed, 1 skipped` + GOLDENS-CLEAN + vitest `7 passed` +
  typecheck/build exit 0; CI `success` on both runs for `d5a5393`.
