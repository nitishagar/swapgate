# SwapGate — Build Plan (MVP v0.1.0)

Open-source model-swap eval gate. Trace → evals → replay → swap receipt.
Apache-2.0. Zero-dependency Python core (stdlib only), thin TS SDK, GitHub Action, docs site.

Source analysis: YC Winter 2027 RFS feasibility doc (S1 "SwapGate", score 51/60, GO).
MVP slice: doc's 0–8 week narrow MVP — CLI (`capture`, `build-evals`, `compare`),
LiteLLM + sec-MCP ingestors, pluggable judges, Markdown/HTML report + decision-receipt JSON,
GitHub Action failing the PR on regression, Bharat pack v0.

## 1. Repo layout

```
swapgate/
  PLAN.md  README.md  LICENSE  CONTRIBUTING.md  SECURITY.md
  pyproject.toml                 # hatchling, package swapgate, [project.scripts] swapgate
  src/swapgate/
    __init__.py                  # __version__
    cli.py                       # capture | build-evals | compare | report | verify | serve-mcp
    traces.py                    # TraceEvent dataclass + JSONL io
    ingest/
      litellm.py                 # StandardLoggingPayload + {messages,response,model} shapes
      otel.py                    # OTel GenAI span JSON (gen_ai.* attributes)
      secmcp.py                  # sec-MCP tool-call log JSONL (defined here; no upstream exists yet)
    redact.py                    # lexvault-style pseudonymiser, profiles: default, dpdp-strict
    cluster.py                   # offline n-gram/MinHash clustering + template extraction
    evals.py                     # EvalSuite/EvalCase schema, rubric synthesis, approval gate
    runner.py                    # asyncio replay vs OpenAI-compatible endpoints + mock provider
    judges/
      base.py                    # Judge protocol, Verdict(choice/score/boolean + probability)
      deterministic.py           # exact / contains / regex / json-schema-subset
      llm.py                     # OpenAI-compatible LLM-as-judge (recordable fixtures)
      typed.py                   # typed-decision judge w/ pluggable backends (local heuristic)
    compare.py                   # baseline-vs-candidate stats, regression rule, thresholds
    receipt.py                   # decision-receipt JSON, sha256 chain + HMAC-SHA256 signature
    report.py                    # Markdown + HTML report render
    mcp_server.py                # stdio JSON-RPC MCP server: compare_models, list_evals
    india.py                     # Bharat pack: Hinglish templates, DPDP profiles, FREE-AI mapping
  tests/                         # pytest, offline, no keys/network (see §3 gates)
  fixtures/                      # sample traces (litellm/otel/secmcp), suites, judge fixtures
  examples/
    sarvam-swap/                 # mock-provider swap demo + checked-in sample report
  action/                        # composite GitHub Action (setup-python, pip install, compare)
  packages/swapgate-js/          # thin TS SDK: types, verifyReceipt, CLI runner client + vitest
  docs/                          # GitHub Pages static site, pi.dev-like warm theme
  .github/workflows/
    ci.yml                       # G0–G5 gates
    pages.yml                    # deploy docs/
```

## 2. Key design decisions

- **Zero-dep core**: stdlib only (`argparse`, `dataclasses`, `asyncio`, `urllib`,
  `hashlib/hmac`, `json`). Dev dep: `pytest` only. Rationale: offline/air-gap story,
  trivial install, no supply-chain risk for a security-adjacent tool.
- **Receipt integrity**: canonical JSON → sha256 content hash + HMAC-SHA256 signature
  with a local key file (`~/.swapgate/key`, 0600). Tamper-evident, offline. Documented
  upgrade path to Ed25519.
- **sec-MCP format defined here**: workspace has no sec-MCP code yet, so `ingest/secmcp.py`
  defines and validates the tool-call log schema it will consume.
- **No co-author attribution**: no `Co-authored-by` trailers, no agent credit in code/docs.
- **Env**: project-local `.venv` via `uv` (`uv venv`, `uv pip install -e '.[dev]'`).

## 3. Gates (each gate = automated tests, all offline except L)

| Gate | What passes | How verified |
|---|---|---|
| G0 unit | every module: ingest×3, redact, cluster, evals, judges×3, compare, receipt, report, bharat | `pytest` full suite, no network/keys |
| G1 CLI e2e | `capture`→`build-evals`→`compare` on fixtures w/ mock provider; golden receipt+report byte-stable apart from timestamps | `pytest tests/test_cli_*.py` + `tests/test_golden.py` |
| G2 regression behaviour | injected candidate regression fails `compare` (exit 2) and Action; parity passes (exit 0) | `pytest tests/test_compare.py::test_regression*`, Action self-test job in CI w/ mock |
| G3 judge reliability | deterministic judges on fixtures; LLM-judge against recorded fixtures (no live calls) | `pytest tests/test_judges_*.py` |
| G4 receipt integrity | verify accepts genuine, rejects tampered/unsigned/wrong-key | `pytest tests/test_receipt.py` |
| G5 site+packaging | docs links resolve, `pip install` from sdist works, Action metadata valid, TS tests pass | `pytest tests/test_docs.py` + CI jobs (`npm --prefix packages/swapgate-js test`) |
| L live (opt-in) | replay vs real OpenAI-compatible endpoint | `SWAPGATE_LIVE=1 pytest -m live`, skipped otherwise |

CI (`ci.yml`): `uv`-installed env → G0–G5 → Action self-test (regression + parity).
`pages.yml`: deploy `docs/` to GitHub Pages.

## 4. CLI contract

```
swapgate capture --from litellm|otel|secmcp --in traces.jsonl --out events.jsonl [--redact dpdp-strict]
swapgate build-evals --in events.jsonl --out suite.json [--clusters k] [--approve]   # approval gate: writes suite.pending.json until --approve with reviewed file
swapgate compare --suite suite.json --baseline mock:parity --candidate mock:regress --judge deterministic --out receipt.json [--report report.md] [--fail-under 0.95 --max-regression 0.02]
swapgate report --receipt receipt.json --format md|html --out report.ext
swapgate verify --receipt receipt.json [--key path]
swapgate serve-mcp [--suite suite.json]   # stdio MCP server
```

Providers: `mock:<scenario>` (parity|regress|seed-N, deterministic offline),
`openai-compat:<base-url>/<model>` (env `SWAPGATE_API_KEY`), `litellm-passthrough` (doc'd, live only).

## 5. Docs site (GitHub Pages, pi.dev-like)

Static `docs/`: `index.html`, `quickstart.html`, `cli.html`, `concepts.html`, `bharat-pack.html`,
`style.css`, no build step, no external assets. Theme from pi.dev tokens:
warm dark canvas `#161d27`/`#0d1116`, parchment text `#dacbc2`/`#ebe7e4`,
terracotta accent `#b86b52`, serif display (Georgia stack — no licensed fonts),
mono code (ui-monospace stack), light/dark toggle via `prefers-color-scheme` + localStorage.

## 6. Milestones this session

1. Scaffold + core modules + fixtures. 2. G0–G4 tests green. 3. Action + TS SDK + G5.
4. Docs site + example report. 5. `gh repo create nitishagar/swapgate --public`, push (no co-author),
   enable Pages. 6. Full `pytest` + report.

## 7. Kill criteria (from doc, unchanged)

Day 90: <300 stars or <50 weekly installs → keep as sec-MCP feature, drop hosted plans.
Day 180: <10 paying or <$200 MRR → kill hosted tier.
(Cut early: the hosted API + teams + billing tier was removed — SwapGate is
CLI + scheduler + MCP + SDK only.)
If a major gateway ships a native equivalent before day 90 → pivot to integration plugin.
