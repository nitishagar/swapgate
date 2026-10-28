# Swap receipt: PASS

Suite `indic-support` v0.1.0 — 4 cases, judge `deterministic`.

- Baseline: `mock:parity` pass rate **0.5**
- Candidate: `mock:seed-7` pass rate **0.5**
- Regression gap: **0.0** (floor `0.5`, max gap `0.5`)
- Issued: 2026-10-28T05:29:07.010858+00:00
- Content hash: ``

## Cases

| case | baseline | candidate | regressed |
|---|---|---|---|
| `indic-support-c00-0002` | fail | fail | no |
| `indic-support-c01-0000` | fail | fail | no |
| `indic-support-c02-0003` | pass | pass | no |
| `indic-support-c03-0001` | pass | pass | no |

_Verify: `swapgate verify --receipt receipt.json` (none)_
