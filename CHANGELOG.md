# Changelog

All notable changes to SwapGate. Format follows Keep a Changelog; versioning is
SemVer. Release tagging is the maintainer's call.

## [0.2.1] - 2026-10-28

### Added

- README for the npm SDK (`swapgate` package page no longer renders empty).

## [0.2.0] - 2026-10-28

### Added

- Local-tracing end-to-end harness: in-process LiteLLM (`mock_response`,
  telemetry off) driving the real CLI capture→build/approve→compare→verify
  chain, plus a `Local-tracing e2e` CI job and the `.[e2e]` test extra.
- LLM-synthesised rubrics: `build-evals --rubrics llm` with recorded-fixture
  offline mode; heuristic synthesis stays the default.
- Scheduled regressions: `run-scheduled` with interval entries, single-flight
  claims, approval refusal, and an append-only SQLite run history; weekly CI
  self-test.
- Hosted tier: localhost JSON API (`serve`) with team API keys (`teams
  create`), per-team run/receipt reads, and test-mode Stripe+Razorpay webhook
  receivers (real SDKs, record-only ledger); `Dockerfile` + container smoke CI.
- sec-MCP v1 log contract (`schemas/secmcp-log-v1.json`) with a reference
  emitter and an emit→capture round-trip e2e.
- Distribution: `swapgate manifest` generating root `mcp.json` (CI drift
  check), PyPI/npm publish workflows (trusted publishing/provenance), and the
  first generated swap report (`examples/swap-reports/`, `docs/reports/`).
- Dependency-diet guard test: extras must never leak into `src/` (scoped
  `billing.py` allowlist for the `hosted` extra).

### Changed

- Markdown reports neutralize ```` ``` ```` runs inside interpolated outputs.
- `build-evals --approve` and `finalize_pending` stamp `metadata.approved`.
- Judge selection shared via `judges.get_judge` (CLI behavior unchanged).
- Docs: new Hosting page, sec-MCP contract section, Reports index.

## [0.1.0] - 2026-10-28

Initial release: capture (LiteLLM/OTel/sec-MCP), redaction profiles, offline
clustering, approval-gated eval suites, mock + OpenAI-compatible replay,
deterministic/LLM/typed judges, signed swap receipts, Markdown/HTML reports,
stdio MCP server, GitHub Action, TypeScript SDK, India pack, docs site.
