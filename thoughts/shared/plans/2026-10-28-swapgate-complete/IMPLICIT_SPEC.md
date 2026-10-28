<!-- SIGNPOST | 1/5: SPEC | requirements only, no designs | Next: PLAN.md
     Pipeline: SPEC -> PLAN -> PLAN_VALIDATION -> implement+review -> tests+TEST_VALIDATION -> green -->
# SwapGate completeness — Implicit Spec

Seeded from `thoughts/shared/research/2026-10-28-swapgate-complete-feature-set.md` (commit `9a80a67`, staleness-clean).
Requirements only. Anything mechanistic here would be exempt from validation — mechanisms live in PLAN.md.

## Preserved invariants (from research; must hold after every phase)

- **Exit-code contract.** 0 pass / 2 gate fail / 1 usage error; Action maps nonzero→`passed=false`.
- **Gate rule.** Fail iff `candidate < fail_under` OR `(baseline − candidate) > max_regression`; empty suites pass vacuously; receipt rates rounded to 4dp.
- **Receipt canonical bytes.** Sorted keys, compact separators, integral floats as ints, bools distinct; `content_hash` only over volatile-free dicts.
- **Receipt signature.** HMAC-SHA256(key, content_hash hex), scheme `hmac-sha256-v1`; TS mirror byte-compatible for the receipt shape (pinned by the shared signed golden).
- **Unsigned shapes.** CLI (`"none"` + empties) and MCP (hash present, signature keys absent) stay distinct; both fail `verify`.
- **Approval before run.** No runnable suite without pending→approve; CLI-inline and lib-helper behaviors stay aligned.
- **Capture lossiness.** Corrupt JSON skipped+counted; parser-`None` skipped+counted; parser-raise aborts. No silent conversion either way.
- **TraceEvent compatibility.** Unknown keys dropped; `trace_id`/`model` required.
- **Check vocabulary.** 7 deterministic types; unknown type fails the check, never raises; empty rubric vacuous-pass (deterministic only).
- **LLM-judge protocol.** Exactly one completion; first-line grammar; unparseable→needs_review; empty rubric still calls (judge-dependent).
- **Typed labels.** pass/fail/needs_review with the `(0.4, 0.7)` band and `passed=False, p=0.5` on review.
- **Error-type surface.** Each surface keeps its observed types (CLI `SystemExit`, MCP `ValueError`, per-check fail, unknown-provider `ValueError`, unknown-`mock:` silent parity fallthrough).
- **Redaction.** Deterministic pseudonyms; fixed profiles; messages+output only (tool_calls/usage/metadata pass through).
- **Mock determinism.** Byte-exact fixed scenarios; goldens depend on them.
- **Report escaping.** HTML escapes; Markdown does not (fence-breakage is the observed behavior until a phase explicitly changes it, with a criterion).
- **Report dispatch.** `.md`→Markdown, else HTML.
- **Runtime diet.** Core stays stdlib-only, Python ≥3.10. New runtime deps need justification; test-only deps live in extras.
- **Docs asset isolation.** Zero fetched external assets.
- **Replay concurrency.** Semaphore-bounded default 8; one provider exception fails the run with no partial receipt.
- **Retry/partial-failure absences.** No live retry (single 60s timeout); no threshold range guards. A phase may add these only as named, tested behavior.
- **Live-payload compatibility.** `StandardLoggingPayload`-shaped payloads parse via `parse_litellm` identically to fixtures.
- **Local-e2e hermeticity.** Default test path runs without keys and with no intentional network use (absolute egress-proof is unobservable in CI, so "no egress" is not claimable — corrected per validation F18); live stays behind `SWAPGATE_LIVE=1`.

## New invariants (completeness scope; hold from the phase that introduces them)

- **Scheduled runs are receipt-identical.** A scheduled comparison produces the same receipt bytes (modulo volatile fields) as the equivalent CLI invocation.
- **Run history is append-only.** Stored runs are never mutated; re-runs create new records.
- **Team isolation.** One team's suites/runs/receipts/keys are unreadable and unusable by another team; key leakage across teams is a P0 defect.
- **Billing test-mode containment.** No live-money code path exists; test/sandbox credentials only; production keys are rejected by shape.
- **Registry manifests are generated, not hand-edited.** Published manifests derive from in-repo sources so they cannot drift.
- **E2E gates are hermetic in CI.** The local-tracing e2e runs on stock runners with no secrets, no intentional network use beyond pip install, telemetry disabled.
- **New-command exit codes.** `run-scheduled`: 0 all-pass-or-none-due / 2 any gate fail / 1 error. `manifest --check`: 0 clean / 1 drift. `serve`: 0 clean shutdown / 1 bind/config error.
- **Scheduled approval refusal.** The scheduler refuses unapproved suites (missing approval stamp) and any `.pending.json` input — exit 1, no run recorded.
- **Scheduled failure records.** A provider exception during a scheduled run records a failure row (NULL receipt) and exits 1; `last_run` advances only after a completed run.
- **Hosted threshold validation.** `fail_under`/`max_regression` must be finite numbers in [0,1]; anything else is a 400 with no run recorded.
- **Webhook idempotency.** Each provider event id is processed at most once; duplicates return success without reprocessing.
- **Team error indistinguishability.** Invalid keys → 401; valid key + foreign record → 404 (never 403), so record existence is not oracle-able.

## Bounding assumptions (user-confirmed 2026-10-28 unless noted)

- Full six-area scope in one plan: hosted tier, billing (test-mode), scheduled runs, team sharing, LLM rubrics, sec-MCP integration, registry distribution + first public swap report (user: "Full: all six areas").
- E2E gates run in CI and locally (user: "CI + local").
- Billing uses real provider SDKs in test/sandbox mode; user supplies test keys as CI secrets during implementation (user: "Test-mode providers", confirmed again 2026-10-28 vs stdlib alternative).
- Runtime diet scoped relaxation (user-confirmed 2026-10-28): the core gate path (capture→compare→verify) stays stdlib-only; `billing.py` alone may depend on a `hosted` extra (stripe, razorpay), imported lazily so base installs are unaffected.
- Single-instance hosted deployment; Postgres migration and multi-instance operation are out of scope (planner bound; see NOT Doing).
- Suites stay small; no perf work (research bound).
- HMAC receipts remain non-third-party-verifiable; Ed25519 stays a documented future (research bound).
- Release tagging is the user's call, not an implementer action.

## Intent open questions — closed

- [x] Hosted tier with Stripe+Razorpay? → Answered: yes, test-mode (Q3).
- [x] Scheduled regressions? → Answered: yes, in scope (Q1).
- [x] Team sharing? → Answered: yes, in scope (Q1).
- [x] LLM-synthesised rubrics? → Answered: yes, in scope (Q1).
- [x] sec-MCP gateway integration? → Answered: yes, in scope (Q1).
- [x] MCP-registry distribution? → Answered: yes, in scope (Q1).
- [x] Public swap reports? → Answered: yes — first report is the distribution proof (confirmed assumption under Q1 "full").
