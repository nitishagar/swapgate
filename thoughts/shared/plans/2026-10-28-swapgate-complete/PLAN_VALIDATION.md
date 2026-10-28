<!-- SIGNPOST | 3/5: PLAN_VALIDATION | adversarial review of PLAN.md against IMPLICIT_SPEC.md
     Prev: PLAN.md | Next: implement+review -->
# SwapGate completeness — Plan Validation (Round 2)

Reviewer: adversarial-plan-reviewer-2 (did not write the plan).
Inputs read fully: `IMPLICIT_SPEC.md`, `PLAN.md` (Revision 2),
research `2026-10-28-swapgate-complete-feature-set.md` (Verification Surface
section), `thoughts/shared/VERIFICATION_SURFACE.md`, plus round-1
`PLAN_VALIDATION.md` (MAJOR-FAIL, 22 findings — every claim below was
re-derived from code, not trusted; this file overwrites round 1).
Scale: SMALL. Default: every item FAIL until the plan earns PASS with evidence.

## Method

Independently re-derived at small depth: (a) each spec invariant (22 preserved
+ 13 new + scoped Runtime-diet relaxation + hermeticity correction) → named
mechanism in plan, (b) blast radius from actual callers via grep + file reads,
(c) each success criterion checked for command + observable + localization +
failing-invariant mapping. Code re-read: `src/swapgate/cli.py`, `evals.py`,
`compare.py`, `runner.py`, `receipt.py`, `report.py`, `mcp_server.py`,
`ingest/{litellm,secmcp}.py`, `judges/{llm,typed,deterministic,base}.py`,
`traces.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `action/action.yml`,
`tests/test_{cli,docs,evals,report,runner,mcp,receipt,golden}.py`,
sibling litellm clone (`__init__.py:240`, `custom_logger.py` hook signatures).

Plan citations spot-checked and correct: `pyproject.toml:17`
(`dependencies = []`), `ci.yml:18` (`python -m pytest -q`), `cli.py:19`
(`finalize_pending` import), `cli.py:76/106/118/129`, `mcp_server.py:36/108/112`,
`test_evals.py:34,43,54,63`, `test_report.py:23,33`, `test_docs.py:9` (`PAGES`),
`test_golden.py:10` (`VOLATILE`), `receipt.py:49` (`0o600`), litellm
`telemetry = True` + `log_{success,failure}_event(kwargs, response_obj,
start_time, end_time)` hook shape. No literal TBD/TODO/FIXME in plan or spec
(grep clean). These pass; everything below did not earn it.

## Important findings

### R2-F1. Hosted API bypasses the approval gate; lib-helper stamp misaligns — PLAN.md:74,89 vs IMPLICIT_SPEC.md:15
- `POST /v1/compare` accepts an inline suite object with no approval check,
  while the scheduler refuses unapproved suites. Spec Approval invariant ("No
  runnable suite without pending→approve") has no mechanism on the hosted path.
  Either hosted needs the `metadata.approved` check or the spec needs a stated
  hosted exemption — neither exists.
- `--approve` stamps `metadata.approved` only in the `cmd_build_evals` CLI
  branch. `finalize_pending` (`evals.py:108`, kept "for API users") does not
  stamp, so lib-finalized suites are scheduler-refused — breaking the spec's
  "CLI-inline and lib-helper behaviors stay aligned."
- The P3 CI fixture (`examples/scheduled/`) must carry `metadata.approved` or
  `run-scheduled --force` exits 1; the stamp requirement on the fixture is
  unnamed. Checklists (1)/(12) FAIL.

### R2-F2. Billing production-key shape rejection has no mechanism — PLAN.md:93 vs IMPLICIT_SPEC.md:38
Spec requires "production keys are rejected by shape." The plan checks Stripe
`livemode==false` (an event field, not a key shape) and a Razorpay account
allowlist (not a key shape), and takes webhook secrets from env with no shape
validation. Nothing rejects a live-shaped secret. Rev 2 dropped round-1's
shape test without amending the spec sentence. No mechanism, no test.
Checklist (1)/(7) FAIL.

### R2-F3. `serve` exit codes unnamed and untested — PLAN.md:88-89 vs IMPLICIT_SPEC.md:41
Spec New-command exit codes require `serve`: 0 clean shutdown / 1 bind/config
error. `run-scheduled` and `manifest --check` codes are named; `serve` codes
appear nowhere in Changes or criteria. No criterion fails on violation.
Checklist (1)/(7) FAIL.

### R2-F4. Scheduler single-flight claim is unimplementable; crash leaks the claim — PLAN.md:74,76
"Single-flight claim in one `BEGIN IMMEDIATE` transaction" is a sqlite
primitive applied to schedules that live in a JSON file (`./schedules.json`).
The claim representation (claims table? which DB? keyed how?) is unnamed —
`history.py` names only `runs` (+`webhook_events` reserved) with no claims
table. No TTL or release on crash: a mid-run crash leaves the claim held
(skip-forever) or unheld (re-run cyclessly) — unspecified. State is not
released on the failure path. Checklist (2)/(12) FAIL.

### R2-F5. Webhook event-id paths and dedup atomicity unnamed — PLAN.md:93
- "Dedup on provider event id" names no JSON extraction path per provider.
  Stripe's `event.id` exists post-`construct_event`; Razorpay's webhook body
  has no documented top-level delivery id (idempotency there is typically
  event-type + payment id) — a stranger cannot implement "the" Razorpay event
  id from this.
- Insert-vs-process order is unnamed. Insert-first loses the event on a crash
  between insert and processing (retry returns 200 no-op for unprocessed
  work); process-first double-processes on crash. Checklist (2)/(12) FAIL.

### R2-F6. `rubric_source` threading unnamed; caller enumeration incomplete — PLAN.md:35,62-63
`build_suite` (`evals.py:100-101`) delegates through `build_suite_from_clusters`
(`evals.py:79`, called at `evals.py:101`, `tests/test_evals.py:74`) to
`synthesize_rubric` (`evals.py:68`, called at `evals.py:92`,
`tests/test_evals.py:27`). The plan adds `rubric_source` to `build_suite` only
and never says whether the LLM branch threads through `build_suite_from_clusters`
(signature change, more callers) or duplicates case-id/tag logic inside
`build_suite` (divergence risk). The enumeration omits all of these plus the
`compare` test callers (`tests/test_compare.py:30,37,45,52,58`). The cited
callers are accurate but the set is incomplete and hides a wiring gap.
Checklist (3) FAIL.

### R2-F7. Hosted judge errors and threshold type coercion unnamed — PLAN.md:89
`POST /v1/compare` takes a `judge` field, but unknown-judge mapping is unnamed
(CLI raises `SystemExit`, MCP raises `ValueError` — hosted needs its own, e.g.
400). "Thresholds validated finite in [0,1] else 400" covers range but not
type: a string threshold raises `TypeError` (→500) under a naive comparison
instead of the specified 400. Spec Error-type surface is incomplete for the new
surface. Checklist (1) FAIL.

### R2-F8. Scheduled/NULL-team row visibility unnamed — PLAN.md:89,91
`GET /v1/runs` returns "caller's team"; scheduler/local rows carry
`team_id=NULL`. `WHERE team_id=?` hides them from everyone; `... OR NULL`
leaks them across teams. The filter is unnamed, so Team isolation is
unimplementable at the read path. Checklist (1) FAIL.

### R2-F9. Reports page escapes the asset-isolation gate — PLAN.md:123 vs `tests/test_docs.py:9`
P6 adds `docs/reports/001-open-weights.html` plus a link-index test, but never
adds it to `PAGES`. `test_no_external_assets` and `test_every_page_links_home`
iterate `PAGES` only, so a CDN-fetching or title-less report page passes every
criterion. (Round-1 F15 fixed for `hosting.html`, reproduced for reports.)
Checklist (1)/(7) FAIL.

### R2-F10. `manifest --check` exit-1-on-drift has no failing test — PLAN.md:119,124-125
Tests pin "regeneration byte-identical; tool parity", and P6 Local runs
`--check` only in the clean state (exit 0). Nothing creates drift and asserts
exit 1, so a `--check` that always exits 0 passes everything. Spec N7 half
unmapped. Checklist (7) FAIL.

### R2-F11. Unsigned shapes have no pinning test — PLAN.md:34 vs `cli.py:114`, `mcp_server.py:44-46`
"Untouched code paths, existing tests" is false as a pinning claim: no existing
test asserts the CLI shape (empty hash/signature + `"none"`) — the unsigned CLI
path only asserts the receipt file exists (`test_cli.py:70-74`) — and none
asserts MCP signature-keys-absent (`test_mcp.py:49` asserts `content_hash`
present only). `test_receipt.py:47-50` pins `verify` rejection, not the
produced shapes. A P7 re-run cannot fail if either shape drifts. Checklist (7)
FAIL.

### R2-F12. Billing lazy-import discipline unenforced — PLAN.md:30,48,93 vs IMPLICIT_SPEC.md:53
The scoped relaxation requires `billing.py` to import SDKs lazily so base
installs are unaffected. The import-guard test checks SDK-name presence under
`src/` except a `billing.py` allowlist — a top-level `import stripe` in
`billing.py` passes the guard yet breaks every base install that transitively
imports it (and the `serve.py`→`billing` import discipline, lazy or top-level,
is itself unnamed). No test imports the hosted path without the `hosted` extra.
Checklist (1)/(7) FAIL.

### R2-F13. Per-phase CI greenness and push-dogfood commands lack criteria — PLAN.md:50,78,95
- P1 adds the `e2e-tracing` job and P3 adds the weekly/`workflow_dispatch` job,
  but no phase criterion asserts those jobs green (only P4's smoke job and P6's
  manual `publish.yml` check are covered). A broken job definition passes all
  phase gates.
- "Push runs execute the identical commands so the path is PR-verifiable"
  names no commands and no push trigger/step — unexecutable as written.
  (Round-1 F13 residual.) Checklist (7)/(12) FAIL.

### R2-F14. P4 and P5 end-to-end criteria are not stranger-executable — PLAN.md:100,109-110,113
- P4: the curl invocation (port, `Authorization` header, request body) is
  unnamed, and "verifies with `swapgate verify --key <server-key>`" omits the
  required `--receipt` argument (`cli.py:195-198` requires both) — the command
  as written fails.
- P5 E2E ("emitter output through the CLI chain to a verifying receipt") names
  no command and no file; the "e2e round-trip (new)" test file is unnamed
  (contrast P2's named `tests/e2e/test_rubrics_llm.py`). Checklist (7)/(12)
  FAIL.

### R2-F15. `last_run` non-advance on failure unasserted — PLAN.md:74,80
The mechanism ("`last_run` advances only after completed runs") is named, but
the test list ("failure-row + exit 1") names no `last_run` assertion. Nothing
fails if `last_run` advances on a failure row (skip-forever) or on skip.
Load-bearing one-liner, missing. Checklist (7) FAIL.

### R2-F16. Two research Gaps neither closed nor explicitly deferred — PLAN.md:146 vs research:145
Testing Strategy omits "no Python lint/typecheck" (8 new modules, no gate) and
"concurrency/cases-per-cluster not surface-tunable" (P3's "scheduler
observability" does not map to tunability). Checklist (7) requires every Gap
closed or explicitly deferred. Documentation-level, but explicit. FAIL.

### R2-F17. "Interop re-run every phase" overclaimed; P2/P5 E2E skip full pytest — PLAN.md:34,68,113
Design Analysis claims "goldens + interop tests re-run every phase," but P2 E2E
runs only `tests/e2e` and P5 criteria run only the sec-MCP tests — neither runs
`test_receipt.py`/`test_golden.py`, and vitest runs only in P6/P7. A P2/P5
regression outside its own files escapes the phase gate despite "each shippable
and gate-verified." P4's new server-signing path is pinned only by Python-side
`verify`, never against the TS verifier. Checklist (7) FAIL.

## Nits (5 shown; 3 further withheld as count)

- N1. P6 E2E "full pytest + vitest green" names no vitest command; P7 does
  (`npm --prefix packages/swapgate-js test`). Same gate, two densities.
- N2. E2E `swapgate serve` / `swapgate manifest --check` invocations assume an
  installed binary; P1 tests deliberately use `[sys.executable, "-m", ...]`.
  Name the install prerequisite or use `-m` consistently.
- N3. Container SQLite path unnamed: `--history` defaults to
  `./swapgate-runs.db`; the Dockerfile volume mount + in-container path are not
  stated, so the smoke job's persistence story is unimplementable.
- N4. Action step-summary rendering of the fence change (`action.yml` shells
  `swapgate report --format md` → `cli.py:129`) has no criterion; P1's fence
  test covers `to_markdown` only, not the Action output.
- N5. `hosted = ["stripe","razorpay"]` majors "pinned at implementation" defers
  the actual pins to implementation time — acceptable, but the values are
  plan-time TBDs by construction.
- +3 further nits withheld (P5 criteria don't run `test_docs.py` for the
  `concepts.html` edit; P3 single-flight overlap driver — threads vs procs —
  unnamed; `Dockerfile` base-image tag unnamed).

## Checklist verdicts

1. Spec invariant → named mechanism: **FAIL** (R2-F1, F2, F3, F7, F8, F12;
   preserved invariants for untouched surfaces pass by explicit untouched +
   goldens, new invariants mostly named).
2. Retry/partial-failure/concurrency + state release: **FAIL** (R2-F4 claim
   representation + crash release; R2-F5 webhook atomicity; sqlite WAL /
   short-lived conns / rollback and team migration pass).
3. Caller enumeration + back-compat: **FAIL** (R2-F6 threading gap + omitted
   `build_suite_from_clusters`/`synthesize_rubric`/test callers; cited lines
   verified accurate; back-compat design itself is sound).
4. No correctness traded for simpler: **PASS** (interval scheduler, stdlib
   server, minimal-shape harness rows verified against `parse_litellm`,
   stdlib-subset schema test, lossy fence escape all respect their invariants).
5. No unjustified new pattern: **PASS** (sqlite3/server/interval/`asyncio.run`
   bridge/compare_digest all justified; no hand-rolled crypto).
6. No TBDs in plan / no mechanisms in spec: **FAIL on plan** (no literal
   markers, but R2-F4/F5/F7/F8 are de-facto TBDs); **PASS on spec**
   (`billing.py` naming in the relaxation is scoping, not mechanism).
7. Dense success criteria: **FAIL** (R2-F3, F9, F10, F11, F12, F13, F14, F15,
   F16, F17; every phase has Local command+observable+localization and avoids
   bare "tests pass," but 10 invariant→criterion mappings cannot fail and cited
   P4/P5 E2E commands are incomplete).
8. Anti-pattern sweep: **FAIL** (retained claim state R2-F4, webhook dedup
   ordering R2-F5; no DI/abstraction, hand-rolled crypto, dev-scale I/O,
   locking, or premature-config issues found).
9. Decomposition: single small plan confirmed; **PASS** (fence escaping in P1
   precedes the P6 frozen report; P7 touches no renderer; sarvam example
   regenerated in-phase — round-1 F17 verified fixed).
10. Defect fixes: confirmed none — P7 pins/escaping are spec-allowed explicit
    changes, dead-import removal is cleanup. **PASS**.
11. Intent open questions: all seven closed in spec and covered by plan scope
    (hosted P4, scheduled P3, teams P4, LLM rubrics P2, sec-MCP P5, registry +
    report P6). **PASS**.
12. Stranger-implementable: **FAIL** (R2-F1 fixture stamp, F4 claim table, F5
    event-id paths, F6 wiring branch, F13 push commands, F14 curl/P5 command,
    N3 volume path).

## Round-1 recheck (independent; not trusted)

Verified fixed: F1 (SDKs adopted), F3 (sqlite discipline), F5 (key mgmt), F6
(hosted→history), F9 (manifest target/path/CI), F10 (bridge + test), F11
(drop-based validation + fixtures format), F12 (minimal shape + `-m`
subprocess), F16 (index test), F17 (fence first), F18 (spec-corrected +
telemetry assertion), F21 (emitter input + generate.py), F22 (diff commands),
all 10 nits. Partially fixed / residual: F2 (paths + failure rows named, claim
representation still missing → R2-F4), F4 (contract named, judge/approval gaps
→ R2-F1/F7), F7 (constructions + dedup named, paths/atomicity/shape missing →
R2-F2/F5), F8 (compare_digest + 404 named, read-path scoping missing → R2-F8),
F13 (smoke/manual honest, per-phase CI missing → R2-F13), F14 (two of three
commands → R2-F3), F15 (hosting fixed, reports repeat → R2-F9), F19
(scheduler fixed, hosted open → R2-F1), F20 (file:line added, set incomplete
→ R2-F6). Round-1's evidence I could not reproduce: none — its code citations
re-verified, but its F20 enumeration shared R2-F6's test-caller omission.

## VERDICT: MAJOR-FAIL

Rev 2 is a large, honest improvement — 14 of 22 round-1 findings fully fixed,
all nits closed, every code citation verified accurate — but it is still not
implementable as written: the hosted surface bypasses approval (R2-F1) and
leaves serve codes, judge errors, and team-read scoping unnamed (R2-F3/F7/F8);
billing's spec-mandated shape rejection has no mechanism (R2-F2); the two
new stateful designs (scheduler claims R2-F4, webhook dedup R2-F5) are missing
their load-bearing details with state unreleased on failure paths; the P2
wiring branch is unnamed with an incomplete enumeration (R2-F6); and ten
spec invariants map to criteria that cannot fail (R2-F9–F17). Fixing this is a
structural revision of Phases 2–4 plus criterion hardening in Phases 1, 5, 6 —
not localized polish.
