# Swap report 001: support-desk rehearsal (mock providers)

Methodology: traces produced by in-process LiteLLM (`mock_response`, telemetry
off), ingested via `capture --from litellm`, clustered into an eval suite,
human-approved, then replayed with `compare --baseline mock:parity
--candidate mock:seed-3`. Mock providers prove gate mechanics only; this report
makes no claims about any real model. Reproduce with
`examples/swap-reports/generate.py`.

## Live rerun (documented, not executed)

To replay the same suite against live OpenAI-compatible endpoints instead of
mocks, export `SWAPGATE_API_KEY` and replace the `compare` step with e.g.:

    swapgate compare --suite s.json \
      --baseline "openai-compat:https://api.vendor-a.example/v1|model-a" \
      --candidate "openai-compat:https://api.vendor-b.example/v1|model-b" \
      --fail-under 0.8 --max-regression 0.1 --out r.json --report report.md

No live run was performed for this report; the numbers below are mock-only.

# Swap receipt: PASS

Suite `report-001` v0.1.0 — 5 cases, judge `deterministic`.

- Baseline: `mock:parity` pass rate **0.2**
- Candidate: `mock:seed-3` pass rate **0.2**
- Regression gap: **0.0** (floor `0.0`, max gap `0.5`)
- Issued: 2026-10-28T07:28:31.200481+00:00
- Content hash: ``

## Cases

| case | baseline | candidate | regressed |
|---|---|---|---|
| `report-001-c00-0003` | fail | fail | no |
| `report-001-c01-0002` | fail | fail | no |
| `report-001-c02-0000` | fail | fail | no |
| `report-001-c03-0004` | fail | fail | no |
| `report-001-c04-0001` | pass | pass | no |

_Verify: `swapgate verify --receipt receipt.json` (none)_
