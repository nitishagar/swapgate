---
date: 2026-10-28T11:05:48+05:30
researcher: Nitish Agarwal
git_commit: 9a80a675b001942ea728402f6d89a392e2342250
branch: main
repository: nitishagar/swapgate
topic: "On the complete feature set not just the MVP."
tags: [research, codebase, swapgate, eval-gate]
scale: small
status: complete
last_updated: 2026-10-28
last_updated_by: Nitish Agarwal
---

# Research: SwapGate complete feature set (beyond MVP)

## Research Question

On the complete feature set not just the MVP.

## Intent

> Lifted from the ticket/user; `not stated` where silent. A record of what was asked — not a spec.

- **Problem**: not stated
- **Proposed outcome**: research coverage of "the complete feature set not just the MVP" (of SwapGate, per the YC Winter 2027 feasibility doc's S1 staged plan), "also cover[ing] one end to end automated testing setup with one of the tracing systems running locally" (scope added mid-research, same episode)
- **Constraints**: not stated in ticket. Prior-session context (not ticket): automated testing at each gate; no co-author attribution; stdlib-only core (`CONTRIBUTING.md:26` [V]).
- **Open questions**: what enumerates the "complete" set? Candidates from the feasibility doc: hosted tier with Stripe+Razorpay? scheduled regressions? team sharing? LLM-synthesised rubrics? sec-MCP gateway integration? MCP-registry distribution? public swap reports? None confirmed; each carried forward, none observable in-repo today (see Gaps).

## Summary

SwapGate v0.1.0 is a single-subsystem, stdlib-only Python CLI+library (~14 modules) that turns production LLM traces into eval suites, replays baseline vs candidate providers, and emits a signed swap receipt gated on a two-part regression rule. Four thin surfaces (CLI, stdio MCP server, composite GitHub Action, TS SDK) wrap one core pipeline. Contracts that matter for any extension: exit codes 0/1/2, the gate rule with 4dp-rounded rates, HMAC-SHA256 receipts whose cross-language interop is pinned by a shared signed golden (mechanisms differ per side — see spec), a two-step human approval gate (CLI inlines it; the lib helper is test-only), and skip-and-count capture that covers corrupt JSON only — parser exceptions propagate. No Python lint/typecheck/benchmark exists; the TS side has tsc. 93 pytest + 7 vitest, all offline except one `SWAPGATE_LIVE=1` test. For a local-tracing e2e, LiteLLM is the evidenced substrate: subclass-`CustomLogger` success/failure callbacks, `mock_response` completions with no keys or network, default-on telemetry that must be disabled for hermetic runs. OTel is excluded (no collector/instrumentation in repo; span production needs both) and sec-MCP is excluded (schema defined, no runnable producer exists).

## Detailed Findings

### Pipeline core (traces → ingest → redact → cluster → evals)

- `TraceEvent` is the canonical record: trace_id/model/messages/output/timestamp/provider/status/tool_calls/usage/metadata — `src/swapgate/traces.py:11` [V]
- `from_dict` drops unknown keys but raises `TypeError` when `trace_id`/`model` are missing — `src/swapgate/traces.py:26-29` [V]
- `read_jsonl_tolerant` skips blank/corrupt lines, returns `(rows, n_skipped)` — `src/swapgate/traces.py:37` [V]
- LiteLLM ingestor returns `None` without coercible messages; failure iff `status_fields.llm_api_status=="failure"` or `error_information` present — `src/swapgate/ingest/litellm.py:55-61` [R]
- OTel ingestor requires a `gen_ai.*` attribute; accepts JSON-blob or flattened `gen_ai.prompt.N.*` attributes — `src/swapgate/ingest/otel.py:27,76` [R]
- sec-MCP ingestor pins `SCHEMA_VERSION=1`, requires `v==1` + `tool`; tool-only records synthesize a user turn; always `status="success"` — `src/swapgate/ingest/secmcp.py:22-53` [R]
- Redaction: 8 regex labels, 3 profiles (default 4 / india 7 / dpdp-strict 8 labels); deterministic `<LABEL_hash6>` pseudonyms via HMAC-SHA256; unknown profile raises `ValueError` — `src/swapgate/redact.py:19-42` [R]
- `redact_event` covers `messages[].content` + `output` only; `tool_calls`/`usage`/`metadata` untouched — `src/swapgate/redact.py:60` [R]
- Clustering: template slotify (`<PII>`/STR`/`<NUM>`) + bigram Jaccard merge at ≥0.5, `max_clusters=8`, long-tail overflow cluster — `src/swapgate/cluster.py:23-53` [R]
- Rubric synthesis: `min_length:1` + up-to-3 `contains` (template words len>4) + conditional `max_length=max(64,3×len)` — `src/swapgate/evals.py:68-76` [V]
- Case ids `{name}-c{ci:02d}-{member:04d}`, `cases_per_cluster=2`, inputs deep-copied, `expected=event.output` — `src/swapgate/evals.py:79-97` [V]

### Replay, judges, comparison

- `MockProvider`: `regress`→fixed refusal; else ≤6 `[A-Za-z]{4,}` keywords echoed; `seed-N` adds `sha256(seed:prompt)[:8]`; unknown `mock:X` falls through to parity text — `src/swapgate/runner.py:48-64` [V]
- `parse_provider` accepts `mock:*` / `openai-compat:<base>|<model>`; `ValueError` otherwise or on missing base|model — `src/swapgate/runner.py:93-102` [V]
- Live provider: urllib POST to `{base}/chat/completions` in a thread, 60s timeout, key from `SWAPGATE_API_KEY`, no retry — `src/swapgate/runner.py:70-90` [V]
- Replay bounded by `Semaphore(max(1, concurrency))`, default 8 — `src/swapgate/runner.py:111-116` [V]
- Verdict auto-labels pass/fail; deterministic judge ANDs checks, score=fraction, empty rubric vacuous-passes — `src/swapgate/judges/base.py:9`, `src/swapgate/judges/deterministic.py:52` [R]
- Check vocabulary: exact/contains/not_contains/regex/min_length/max_length/json_keys; unknown type → `(False, …)` per check, never raises — `src/swapgate/judges/deterministic.py:15` [R]
- LLM judge: one completion, first-line `PASS|FAIL <score> <rationale>` grammar, `pass_threshold=0.5`, unparseable→needs_review; empty rubric renders a fallback prompt and still calls — `src/swapgate/judges/llm.py:15,58-74` [V]
- `FixtureCompleter` raises `KeyError` on unrecorded prompts — `src/swapgate/judges/llm.py:44-47` [V]
- Typed judge: `score>=0.7`→pass, `<0.4`→fail, else needs_review with `passed=False, probability=0.5` — `src/swapgate/judges/typed.py:29-43` [V]
- `regressed = baseline.passed and not candidate.passed`; empty suite rates are 1.0 (vacuous pass) — `src/swapgate/compare.py:27-62` [V]
- Gate: fail iff `candidate < fail_under` (default 0.0) or `gap > max_regression` (default 1.0); rates rounded to 4dp in the summary — `src/swapgate/compare.py:68-89` [V]
- Baseline+candidate replay concurrently via `asyncio.gather`; one provider exception fails the whole run, no partial receipt — `src/swapgate/compare.py:92-104` [V]

### Receipts and reports

- Canonical bytes: bool-safe, integral floats→ints, sorted keys, compact separators — `src/swapgate/receipt.py:21-36` [V]
- Signature is `HMAC-SHA256(key, content_hash_hex)` with scheme `hmac-sha256-v1` — `src/swapgate/receipt.py:64-67` [V]
- Verify requires scheme match + hash match + `hmac.compare_digest`; strips volatile keys before recompute — `src/swapgate/receipt.py:70-77` [V]
- Key file created with mode `0o600`, 32 random bytes hex-encoded — `src/swapgate/receipt.py:43-52` [V]
- Markdown report interpolates regressed outputs raw inside code fences (no escaping); HTML escapes everything — `src/swapgate/report.py:60-68` vs `:78` [V]

### Surfaces (CLI, MCP, Action, TS SDK, docs, examples)

- CLI: 6 subcommands; exit codes `EXIT_OK=0, EXIT_ERROR=1, EXIT_GATE_FAIL=2` — `src/swapgate/cli.py:1-12` [V]
- `capture` has no `try` around `parser(row)` — valid-JSON/misshaped rows that raise crash the run; `build-evals` likewise exposes `from_dict` `TypeError` — `src/swapgate/cli.py:50-51,74-75` [V]
- CLI `--approve` inlines pending-file logic (missing file → exit 1) and never calls `finalize_pending`; that helper is exercised only by `tests/test_evals.py` (dead import at `cli.py:19`) — `src/swapgate/cli.py:64-73` [V]
- Judge selection: CLI raises `SystemExit` on unknown judge / missing `--judge-fixtures`; MCP raises `ValueError` and offers deterministic|typed only — `src/swapgate/cli.py:87-98`, `src/swapgate/mcp_server.py:24-29` [V]
- Unsigned receipts have two shapes: CLI writes empty hash/signature + scheme `"none"`; MCP returns body + `content_hash` with signature keys absent — `src/swapgate/cli.py:114`, `src/swapgate/mcp_server.py:44-46` [V]
- Report dispatch: path ending `.md`→Markdown, anything else→HTML — `src/swapgate/cli.py:118` [V]
- MCP: stdio JSON-RPC 2.0, tools `compare_models`/`list_evals`; errors `-32000`, unknown tool `-32602`, unknown method `-32601` — `src/swapgate/mcp_server.py:58-119` [R]
- Action: composite; installs from `GITHUB_ACTION_PATH/..`; runs `compare --sign`; appends report to step summary *before* the final gate check; always uploads the receipt artifact — `action/action.yml:45-85` [V]
- TS SDK exports receipt types + `canonicalize`/`contentHash`/`verifyReceipt`/`summarize`/`buildCompareArgs` — `packages/swapgate-js/src/index.ts:4-101` [V]
- `buildCompareArgs` covers suite/baseline/candidate/judge/failUnder/maxRegression/out; omits `--report/--key/--sign/--judge-fixtures` — `packages/swapgate-js/src/index.ts:86-101` [V]
- Docs: 5 pages + `style.css`, no fetched external assets (external *hyperlinks* exist); example suite + rendered report checked in — `docs/`, `examples/sarvam-swap/` [R]
- India pack: 5 Hinglish templates, 30-day retention advisory text, 7-key FREE-AI annex map (advisory, unenforced) — `src/swapgate/india.py:14-41` [R]

### Local tracing end-to-end (LiteLLM substrate)

> Evidence below cites the sibling clone `/home/nitish/repos/litellm` at version 1.89.0 (`pyproject.toml:3` [V]) — outside the SwapGate repo. Line numbers are clone-relative.

- Subclass `CustomLogger`, register via `litellm.callbacks`; success/failure hooks receive `(kwargs, response_obj, start_time, end_time)` — `litellm/integrations/custom_logger.py:69,134-137` [V]
- `StandardLoggingPayload` carries `messages`, `response`, `status`/`status_fields`, `custom_llm_provider`, `error_information` — the keys `parse_litellm` reads — `litellm/types/utils.py:2957-2994` [V]
- `mock_response` (str/Exception/dict/ModelResponse) short-circuits `completion()` to `mock_completion` with no network call — `litellm/main.py:1660-1669`, `:792` [V]
- Mock path needs no real key (`api_key="mock-key"`); `litellm.MockException` payloads exercise failure hooks — `litellm/main.py:831`, `:733` [R]
- Proxy runs locally via `litellm --config config.yaml` (default port 4000) — `litellm/proxy/proxy_cli.py:692-696`, `:608-610` [R]
- Usage telemetry defaults ON (`telemetry = True`); proxy opt-out is `--telemetry False` — `litellm/__init__.py:240`, `litellm/proxy/proxy_cli.py:704-708` [V]
- OTel exclusion: SwapGate has no Docker/collector/instrumentation files (glob empty [V]); producing GenAI spans locally requires a collector plus an instrumented producer, neither present
- sec-MCP exclusion: only the consumer exists (`--from secmcp` flag, v1 schema, fixtures, tests); no runnable sec-MCP producer in the workspace (workspace search empty [V])
- No local-tracing e2e exists in SwapGate today: G1 tests are fixture-file-driven (`tests/test_cli.py`, `fixtures/*` [R]); the live path is CI-skipped

### Packaging and config

- Runtime is stdlib-only (`dependencies = []`), `requires-python = ">=3.10"`, entry `swapgate.cli:main` — `pyproject.toml:1-24` [V]
- pytest: `testpaths = ["tests"]`, `live` marker for the opt-in endpoint test — `pyproject.toml:37-41` [V]
- TS: `vitest run` / `tsc --noEmit` / `tsc -p tsconfig.build.json` (strict, ES2022, NodeNext) — `packages/swapgate-js/package.json:11-15`, `tsconfig*.json` [V]
- No Python lint/typecheck/benchmark config or CI step exists (root + depth-2 glob + `ci.yml` checked) — absence [V]

## Implicit Spec — invariants any change here must uphold

> Requirements, not designs.

- **Exit-code contract.** 0 = pass, 2 = gate fail (regression / invalid receipt), 1 = usage error. The Action maps nonzero→`passed=false` (`action/action.yml:71-75` [V]). Edge: uncaught exceptions (e.g. `TypeError` from `from_dict`) surface as tracebacks, still nonzero.
- **Gate rule.** Fail iff `candidate_pass_rate < fail_under` OR `(baseline − candidate) > max_regression` (`src/swapgate/compare.py:68-72` [V]). Empty suites pass vacuously (rates 1.0). Receipt rates are rounded to 4dp — exact-equality checks against unrounded values will flake.
- **Receipt canonical bytes.** Sorted keys, compact separators, integral floats rendered as ints, booleans distinct from ints (`src/swapgate/receipt.py:21-36` [V]). `content_hash` must only ever be computed over volatile-free dicts. Rationale: the TS side has no float normalization — interop holds for the receipt shape only because Python normalizes to `JSON.stringify` form.
- **Receipt signature.** `HMAC-SHA256(key_bytes, content_hash_hex)`, scheme id `hmac-sha256-v1`; verify = scheme match + hash match + constant-time compare (`src/swapgate/receipt.py:64-77` [V]). TS mirrors with `timingSafeEqual` (`packages/swapgate-js/src/index.ts:68-74` [V]).
- **Unsigned shapes are distinct and both unverifiable.** CLI shape: empty hash/signature + `"none"`; MCP shape: `content_hash` present, signature keys absent. `verify` rejects both, for different reasons (`src/swapgate/cli.py:114`, `src/swapgate/mcp_server.py:44-46` [V]).
- **Approval before run.** No runnable suite without the two-step pending→approve flow. Two implementations exist: CLI inline (missing file → exit 1) and lib `finalize_pending` (raises `ApprovalRequiredError`) — keep their observable behavior aligned (`src/swapgate/cli.py:64-73`, `src/swapgate/evals.py:108-116` [V]).
- **Capture lossiness.** Corrupt JSON lines are skipped+counted; valid-JSON rows the parser rejects (`None`) are skipped+counted; valid-JSON rows that *raise* inside a parser abort the run (`src/swapgate/cli.py:45-61` [V]). A change must not silently convert a crash into a skip or vice versa.
- **TraceEvent compatibility.** Unknown keys dropped on read (forward-compatible); `trace_id`/`model` required (`src/swapgate/traces.py:26-29` [V]).
- **Deterministic-check vocabulary.** Seven check types; unknown type fails the check, never raises; empty rubric passes vacuously (`src/swapgate/judges/deterministic.py:15,52` [R]).
- **LLM-judge protocol.** Exactly one completion per evaluation; only the first line parsed against `^(PASS|FAIL) <score> <rationale>`; unparseable → `needs_review` score 0.0 (`src/swapgate/judges/llm.py:54-74` [V]). Empty rubric still calls the completer with a fallback prompt (judge-dependent, unlike deterministic).
- **Typed labels.** Exactly pass/fail/needs_review with `score>=0.7`→pass, `<0.4`→fail, else `needs_review` with `passed=False, probability=0.5` (`src/swapgate/judges/typed.py:29-43` [V]).
- **Error-type surface (observed, inconsistent).** Unknown judge: CLI `SystemExit`, MCP `ValueError`; unknown check type: per-check failure, no raise; unknown provider: `ValueError`; unknown `mock:` scenario: silent parity fallthrough (`src/swapgate/runner.py:48-64` [V]). Any change must preserve each caller's observed type.
- **Redaction determinism and bounds.** Same (key,label,value) → same pseudonym; profiles are fixed label sets; unknown profile raises. Covers messages+output ONLY — PII in `tool_calls`/`usage`/`metadata` passes through unredacted (`src/swapgate/redact.py:42-60` [R]).
- **Mock determinism.** Fixed scenarios; `regress` is the literal refusal; `seed-N` derives from `sha256(seed:prompt)[:8]` (`src/swapgate/runner.py:48-64` [V]). Goldens depend on byte-exact outputs.
- **Report escaping.** HTML escapes all interpolated outputs; Markdown does NOT (fence-breaking outputs corrupt the report) (`src/swapgate/report.py:60-78` [V]).
- **Report dispatch.** `.md` suffix → Markdown, anything else → HTML (`src/swapgate/cli.py:118` [V]).
- **Runtime diet.** Stdlib-only, Python ≥3.10 (`pyproject.toml:6,17` [V]); policy at `CONTRIBUTING.md:26` [V].
- **Docs asset isolation.** Pages fetch zero external assets (external hyperlinks allowed) — enforced by `tests/test_docs.py` [R].
- **Replay concurrency.** Semaphore-bounded, default 8, clamped ≥1; baseline+candidate run concurrently; a single provider exception fails the whole comparison with no partial receipt (`src/swapgate/runner.py:111-116`, `src/swapgate/compare.py:101-104` [V]).
- **Concurrency/retry/partial-failure absences (observed).** No retry on live calls (single 60s timeout); malformed provider payloads raise `KeyError`; no guards on `fail_under`/`max_regression` ranges (`src/swapgate/runner.py:77-90` [V]).
- **Live-payload compatibility.** Payloads shaped per `StandardLoggingPayload` (`messages`/`response`/`status_fields`/`error_information` keys) must parse via `parse_litellm` identically to fixtures — the e2e contract between a local tracer and `capture` (`src/swapgate/ingest/litellm.py` [R] + `litellm/types/utils.py:2957` [V]).
- **Local-e2e hermeticity.** Any local-tracing e2e must run without keys or network (LiteLLM `mock_response` path) and with telemetry disabled (default is on). Rationale: the repo's standing rule keeps keys/network out of the default test path (`CONTRIBUTING.md:15-19` [V]).
- **Bounding assumptions**: suites are small (fixtures ≤5 lines; no suite-size/perf evidence exists); single-user local-key trust (HMAC is tamper-evident, not third-party-verifiable); heuristic rubrics are unreviewed drafts and human review is the only quality control; DPDP 30-day retention and FREE-AI annex are advisory prose, not gates; mocks prove gate mechanics, never model quality.

## Verification Surface

> Feedback loops that already exist. Facts only. Durable copy: `thoughts/shared/VERIFICATION_SURFACE.md` (created this phase).

- **Commands**: test-all `python -m pytest -q` (`.github/workflows/ci.yml:18` [V]) · test-one file/test `pytest -q tests/test_X.py[::test_y]` (derived, not repo-recorded) · TS `npm test` / `npm run typecheck` / `npm run build` (`packages/swapgate-js/package.json:11-15` [V]) · packaging `python -m build --sdist` + sdist-install check (`ci.yml:46-51` [V]) · live `SWAPGATE_LIVE=1 pytest -m live` (`CONTRIBUTING.md:16` [V]) · bench/lint: none — healthy output: `93 passed, 1 skipped` / `7 passed` (observed 2026-10-28, CI green)
- **Oracles**: `tests/golden/receipt.json` (normalized gate verdict [R]) · `tests/golden/signed-receipt.json` (Python↔TS interop, fixed key [V]) · `fixtures/traces-*.jsonl` (synthetic incl. corrupt/failure/PII rows [R]) · sibling paths: 3 judges, 3 ingestors, md/html reports, mock scenarios · `examples/sarvam-swap/report.md` (checked-in, NOT test-asserted [R])
- **Fixtures & harnesses**: `tests/conftest.py` `FIXTURES` helper; `FixtureCompleter` (unknown→`KeyError` [V]); `MockProvider` scenarios [V] — all dev-sized
- **Observability**: CLI stdout lines (counts, PASS/FAIL, VALID/INVALID); pytest/vitest summaries; no logs/metrics/traces/profilers (absence [V])
- **Gaps**: no Python lint/typecheck · no benchmarks · live path unexercised in CI · no local-tracing e2e exists (LiteLLM mock path is the evidenced substrate; OTel/sec-MCP excluded) · unknown `mock:` scenario unpinned by any test · parser-exception behavior unobserved · Markdown fence injection unobserved · concurrency/cases-per-cluster not surface-tunable · example report not asserted · rubric quality unobservable · all six Intent open questions unobservable (future scope, carried forward)

## Hard Cores

> Factual inventory for the planner's decomposition gate — count and name only; no sequencing, scoping, or design.

- Single hard core: preserving the cross-surface gate/receipt contract (exit codes, gate rule, canonical bytes, HMAC interop, approval flow) while extending the MVP toward hosted/multi-user operation.

## Evidence Ledger

| Claim | Evidence | Trust | Load-bearing |
|---|---|---|---|
| Exit codes 0/1/2 | `src/swapgate/cli.py:10-12` | V | yes |
| Gate rule + defaults + 4dp rounding | `src/swapgate/compare.py:68-89` | V | yes |
| Empty suite vacuous pass | `src/swapgate/compare.py:53-62` | V | yes |
| Canonical bytes (sort/compact/float-norm) | `src/swapgate/receipt.py:21-36` | V | yes |
| HMAC-SHA256(key, hash hex) + scheme id | `src/swapgate/receipt.py:64-67` | V | yes |
| Verify: scheme+hash+compare_digest | `src/swapgate/receipt.py:70-77` | V | yes |
| TS canonicalize/verify mirror | `packages/swapgate-js/src/index.ts:50-74` | V | yes |
| TS↔Python mechanisms differ; interop shape-scoped | `index.ts:50-61` vs `receipt.py:21-36` | V | yes |
| Signed golden shared by both suites | `tests/golden/signed-receipt.json` + both test files | V | yes |
| CLI approval inline, exit 1 on missing | `src/swapgate/cli.py:64-73` | V | yes |
| Lib approval raises ApprovalRequiredError | `src/swapgate/evals.py:108-116` | V | yes |
| `finalize_pending` test-only (+dead CLI import) | grep `finalize_pending`; `cli.py:19` | V | no |
| Tolerant JSONL skip+count | `src/swapgate/traces.py:37` | V | yes |
| Parser exceptions propagate (no try) | `src/swapgate/cli.py:50-51` | V | yes |
| from_dict drops unknown, requires ids | `src/swapgate/traces.py:26-29` | V | no |
| CLI vs MCP unsigned shapes differ | `cli.py:114`, `mcp_server.py:44-46` | V | yes |
| Judge error types differ by surface | `cli.py:98`, `mcp_server.py:29` | V | yes |
| LLM judge 1 completion + grammar + fallback | `src/swapgate/judges/llm.py:54-74` | V | yes |
| FixtureCompleter KeyError at :47 | `src/swapgate/judges/llm.py:44-47` | V | no |
| Typed band boundaries + review semantics | `src/swapgate/judges/typed.py:29-43` | V | yes |
| Mock scenarios + silent fallthrough | `src/swapgate/runner.py:48-64` | V | yes |
| Provider grammar + ValueErrors | `src/swapgate/runner.py:93-102` | V | no |
| Live POST, 60s timeout, no retry | `src/swapgate/runner.py:70-90` | V | no |
| Semaphore default 8, clamp ≥1 | `src/swapgate/runner.py:111-116` | V | no |
| Gather fails whole run, no partial | `src/swapgate/compare.py:101-104` | V | yes |
| Markdown raw fences vs HTML escaped | `src/swapgate/report.py:60-78` | V | yes |
| Report dispatch .md→md else html | `src/swapgate/cli.py:118` | V | no |
| Rubric synthesis shape (conditional max) | `src/swapgate/evals.py:68-76` | V | no |
| Case ids + cases_per_cluster=2 | `src/swapgate/evals.py:79-97` | V | no |
| Action composite steps + artifact | `action/action.yml:45-85` | V | yes |
| TS buildCompareArgs flag subset | `index.ts:86-101` | V | no |
| stdlib-only + ≥3.10 + entry point | `pyproject.toml:1-24` | V | yes |
| pytest testpaths + live marker | `pyproject.toml:37-41` | V | yes |
| TS scripts + strict tsconfig | `package.json:11-15`, `tsconfig*.json` | V | yes |
| CI pytest/ts/packaging/selftest steps | `.github/workflows/ci.yml` | V | yes |
| No Python lint/bench configs | root + depth-2 glob + ci.yml | V | yes |
| Ingestor None-conditions + statuses | `ingest/litellm.py:55-61`, `otel.py:76`, `secmcp.py:22` | R | no |
| Redact labels/profiles/determinism | `src/swapgate/redact.py:19-60` | R | no |
| Cluster bigram/0.5/8/overflow | `src/swapgate/cluster.py:23-53` | R | no |
| Deterministic AND/score/vacuous | `judges/deterministic.py:15,52` | R | no |
| MCP tools + error codes | `src/swapgate/mcp_server.py:58-119` | R | no |
| India pack templates/annex advisory | `src/swapgate/india.py:14-41` | R | no |
| Docs offline assets + example checked in | `docs/`, `examples/sarvam-swap/` | R | no |
| Test-file→gate mapping (14 files) | `tests/test_*.py:1` docstrings | R | no |
| LiteLLM callback signature | `litellm/integrations/custom_logger.py:134-137` (clone@1.89.0) | V | yes |
| StandardLoggingPayload keys | `litellm/types/utils.py:2957-2994` (clone@1.89.0) | V | yes |
| mock_response short-circuit, no network | `litellm/main.py:1660-1669` (clone@1.89.0) | V | yes |
| Telemetry default on + proxy opt-out | `litellm/__init__.py:240`, `proxy_cli.py:704-708` | V | no |
| Mock needs no key; MockException path | `litellm/main.py:831`, `:733` | R | no |
| Proxy local command + port 4000 | `litellm/proxy/proxy_cli.py:692-696`, `:608-610` | R | no |
| No collector/Docker in SwapGate | repo glob (empty) | V | no |
| No runnable sec-MCP producer | workspace search (empty) + consumer-only refs | V | no |

## Architecture Insights

- Surfaces are thin: CLI/MCP/Action/TS-SDK all delegate to `compare`/`evals`/`receipt`/`runner`; the Action shells out to the installed CLI rather than importing (`action/action.yml:54,65` [V]). A change to core signatures ripples to 4 surfaces — applicability: any core edit must re-check all four call sites.
- Two signing postures coexist: CLI signs to a key file (or explicitly unsigned); MCP returns hashed-but-unsigned bodies. Callers must treat "has content_hash" ≠ "verified".
- Approval exists twice (CLI inline + lib helper) with different failure modes (exit 1 vs exception); tests pin only the lib path.
- Oracles mirror the trust boundary: goldens pin gate bytes; the signed golden pins cross-language bytes; nothing pins rubric quality, live behavior, or report prose.
- Stdlib-only core + zero-config pytest keeps the feedback loop to one command; the TS package is the only node-dependent surface.

## Coverage & Open Questions

- Searched: full `src/` (16 modules), all 14 test files (headers + targeted bodies), fixtures, goldens, Action, TS SDK src+test+configs, docs (structure), examples, both CI workflows, pyproject, CONTRIBUTING. Modes: by-module, by-caller (finalize_pending callers, buildCompareArgs flag parity), by-test (gate mapping), by-config (pyproject/tsconfigs/Action/pytest markers), by-CI (all 5 jobs + Pages).
- Bounded: audit was 1 round per small profile; `[R]` claims verified by sample (audit confirmed 4/4 sampled + 3/3 [V] with 1 refuted-and-fixed). Line numbers on `[R]` rows are sub-agent-cited, content confirmed via excerpts.
- Scope grew mid-episode (local-tracing e2e): covered by 1 bounded discovery agent + direct verification of its load-bearing claims to [V]. The follow-up was NOT separately audited (small profile allows 1 round, already spent) — residual risk noted, not looped away.
- Residual: ingestor/cluster/redact/deterministic-judge/MCP/India/docs internals remain `[R]` — content backed by excerpts, lines unaudited. Re-verify to `[V]` if the plan touches them.
- Open: the six "complete set" questions (hosted, billing, scheduled, teams, LLM rubrics, distribution) — unobservable in-repo, carried forward to `create_plan_generic_v2_7`. If the code moves materially before planning, re-run follow-up research first.
