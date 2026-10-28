# SwapGate

The open-source model-swap eval gate: production traces become evals, and a
candidate model must pass before you swap. Move from rented frontier APIs to
self-hosted open-weight models (Sarvam, Llama, Qwen) without silent regressions.

```
traces → capture → build-evals → compare → swap receipt (pass/fail)
```

- **Capture** real traffic: LiteLLM callbacks, OpenTelemetry GenAI spans, sec-MCP logs.
- **Redact** before storage: deterministic pseudonymisation, DPDP-aware profiles.
- **Build evals** by clustering traces; a human approves rubrics before they run.
- **Compare** baseline vs candidate with deterministic, LLM, or typed-decision judges.
- **Ship the receipt**: signed JSON verdict + Markdown/HTML report; the GitHub Action
  fails the PR on regression.

Zero-dependency Python core (stdlib only). Apache-2.0.

## Install

```bash
pip install swapgate
# or from source:
git clone https://github.com/nitishagar/swapgate.git
cd swapgate
uv venv && uv pip install -e '.[dev]'
```

## 60-second demo (fully offline)

```bash
swapgate capture --from litellm --in fixtures/traces-litellm.jsonl --out /tmp/events.jsonl
swapgate build-evals --in /tmp/events.jsonl --out /tmp/suite.json --name demo
swapgate build-evals --in /tmp/events.jsonl --out /tmp/suite.json --approve
swapgate compare --suite /tmp/suite.json --baseline mock:parity --candidate mock:regress \
  --fail-under 0.5 --out /tmp/receipt.json --report /tmp/report.md
# exit 2: candidate regressed. Inspect /tmp/report.md, then:
swapgate verify --receipt /tmp/receipt.json --key /tmp/demo.key  # if signed with --key
```

## CLI

| Command | Purpose |
|---|---|
| `capture --from litellm\|otel\|secmcp --in --out [--redact profile]` | Ingest raw traces |
| `build-evals --in --out [--name] [--clusters] [--bharat-pack] [--approve]` | Cluster → suite (approval-gated) |
| `compare --suite --baseline --candidate [--judge] [--fail-under] [--max-regression] [--out] [--report] [--key/--sign]` | Replay + gate (exit 2 on regression) |
| `report --receipt --format md\|html [--out]` | Render a receipt |
| `verify --receipt --key` | Verify a signed receipt |
| `serve-mcp` | stdio MCP server (`compare_models`, `list_evals`) |

Providers: `mock:parity|regress|seed-N` (offline), `openai-compat:<base-url>|<model>`
(live, key from `SWAPGATE_API_KEY`). Exit codes: 0 pass, 2 gate fail, 1 error.

## GitHub Action

```yaml
- uses: nitishagar/swapgate@v0
  with:
    suite: evals/suite.json
    baseline: openai-compat:https://api.example.com/v1|baseline-model
    candidate: openai-compat:https://api.example.com/v1|candidate-model
    fail-under: '0.95'
    max-regression: '0.02'
```

## Gates (automated tests)

Every gate runs offline in CI (`pytest`, no keys/network):

- **G0 unit** — ingest ×3, redact, cluster, evals, judges ×3, compare, receipt, report, Bharat pack
- **G1 CLI end-to-end** — capture→build-evals→compare on fixtures, golden receipt
- **G2 regression behaviour** — injected regression fails (exit 2), parity passes (exit 0)
- **G3 judge reliability** — deterministic fixtures + recorded LLM-judge fixtures
- **G4 receipt integrity** — genuine verifies, tampered/unsigned/wrong-key rejected
- **G5 site + packaging** — docs links, sdist install, Action metadata, TS SDK tests
- **L live** (opt-in) — `SWAPGATE_LIVE=1 pytest -m live` vs a real endpoint

```bash
pytest            # G0–G5 offline
```

## Bharat pack (`--bharat-pack`)

Hinglish eval templates, DPDP redaction profiles (`bharat`, `dpdp-strict`: PAN,
Aadhaar, UPI, +91 phones), 30-day retention guidance, and a FREE-AI control
annex for fintech audit packets. See `docs/bharat-pack.html`.

## Layout

`src/swapgate/` core · `tests/` gates · `fixtures/` sample traces · `action/`
GitHub Action · `packages/swapgate-js/` thin TS SDK · `docs/` GitHub Pages site ·
`examples/sarvam-swap/` mock swap demo.

## Limits

- Heuristic rubrics need human review (the approval gate enforces this); LLM
  rubric synthesis is live-only and not in v0.1.
- Mock providers prove gate mechanics, not model quality.
- HMAC receipts are tamper-evident, not third-party-verifiable (Ed25519 is the
  documented upgrade path).

## License

Apache-2.0. See `LICENSE`.
