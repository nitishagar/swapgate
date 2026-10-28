# Verification Surface — SwapGate

Durable project-level source for how this repo verifies changes. Facts only.
Last verified against commit `9a80a67` on main (2026-10-28).

## Commands

- test-all (Python, offline): `python -m pytest -q` — defined in
  `.github/workflows/ci.yml:18`, documented in `CONTRIBUTING.md:15`.
  Healthy: `93 passed, 1 skipped` (skip = live test without `SWAPGATE_LIVE=1`).
- test-one (Python, one file): `python -m pytest -q tests/test_<name>.py`
  (derived from the repo's runner; no repo-recorded single-test command).
- test-one (Python, one test): `python -m pytest -q tests/test_<name>.py::test_<name>`
  (derived likewise).
- test-all (TS SDK): `npm test` (= `vitest run`) in `packages/swapgate-js` —
  `packages/swapgate-js/package.json:13`. Healthy: `7 passed`.
- test-one (TS): `npx vitest run test/verify.test.ts` in `packages/swapgate-js`
  (derived from the `test` script).
- typecheck (TS only): `npm run typecheck` (= `tsc --noEmit`).
  No Python typecheck/lint is configured (no ruff/mypy/flake8 config or CI step).
- build (TS): `npm run build` (= `tsc -p tsconfig.build.json`).
- packaging: `python -m build --sdist`, then venv-install + `swapgate --version`
  (`.github/workflows/ci.yml:46-51`).
- live (opt-in): `SWAPGATE_LIVE=1 pytest -m live` needs `SWAPGATE_BASE_URL`,
  `SWAPGATE_MODEL` (`CONTRIBUTING.md:16`, `tests/test_runner.py`).
- benchmark: none exists.

## Oracles

- `tests/golden/receipt.json` — normalized `compare` output (volatile fields
  stripped); asserts byte-stability of the gate verdict (`tests/test_golden.py`).
- `tests/golden/signed-receipt.json` — Python-signed receipt with fixed key
  `swapgate-interop-test-key`; asserted by Python (`tests/test_receipt.py`) AND
  the TS SDK (`packages/swapgate-js/test/verify.test.ts`) — the cross-language
  canonical-JSON/HMAC contract.
- `fixtures/traces-{litellm,otel,secmcp}.jsonl` — dev-sized synthetic traces
  (incl. corrupt lines, failure statuses, PII) driving ingest + CLI e2e tests.
- Sibling paths computing the same thing differently: deterministic vs typed vs
  LLM judges (`src/swapgate/cli.py:87-98` selects); `mock:parity` vs
  `mock:regress` vs live `openai-compat` providers; `to_markdown` vs `to_html`.
- `examples/sarvam-swap/report.md` — checked-in sample output; NOT asserted by
  any test (regenerate-and-diff only).

## Fixtures & harnesses

- `tests/conftest.py` — `FIXTURES` path helper. All fixtures dev-sized (≤5 lines).
- `FixtureCompleter` (`src/swapgate/judges/llm.py`) — recorded LLM-judge
  responses; unknown prompts raise (proves offline determinism).
- `MockProvider` scenarios `parity|regress|seed-N` (`src/swapgate/runner.py`) —
  deterministic stand-ins for models.

## Observability

- CLI stdout: `captured N events ... (skipped M)`, `wrote K cases`, review
  prompt, `baseline X candidate Y gap Z -> PASS|FAIL`, `receipt VALID|INVALID`.
- `pytest -q` / `vitest run` summaries. No structured logs, metrics, traces,
  or profilers anywhere in repo or CI.

## Gaps

- No Python lint/typecheck gate.
- No benchmark/profiling harness; no timing assertions.
- Live path (`openai-compat`, LLM rubric synthesis) has no CI coverage (L skipped).
- No end-to-end test spins a local tracing producer (LiteLLM `mock_response` path is the evidenced substrate; see research doc 2026-10-28).
- Example report + docs content not regression-asserted (docs links are).
- Rubric quality itself is unobservable — human review is the only control.

## Project rules

- Core stays stdlib-only (`pyproject.toml:17`); new runtime deps need justification.
- No network/keys in the default test path; live stays behind `SWAPGATE_LIVE=1`.
- Never commit trace data with real PII; fixtures use synthetic identities.
- Commits carry no co-author trailers.
