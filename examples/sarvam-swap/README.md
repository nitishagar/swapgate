# Sarvam swap example

A worked model swap: frontier API baseline vs self-hosted Sarvam-style candidate
on an Indic support suite. Offline here (mock providers prove the gate mechanics);
the same commands run against real endpoints.

## Run (offline)

```bash
swapgate capture --from litellm --in ../../fixtures/traces-litellm.jsonl \
  --out /tmp/sg-events.jsonl --redact india
swapgate build-evals --in /tmp/sg-events.jsonl --out suite.json \
  --name indic-support --india-pack
# review suite.pending.json, then:
swapgate build-evals --out suite.json --approve
swapgate compare --suite suite.json \
  --baseline mock:parity --candidate mock:seed-7 \
  --fail-under 0.5 --max-regression 0.5 \
  --out receipt.json --report report.md
```

`report.md` in this directory is the checked-in output of that run. Note both
providers score 0.5: the heuristic rubrics are unreviewed drafts (see the pending
suite), which is exactly why the approval gate exists — review and tighten them
before trusting the verdict.

## Run (live, Sarvam on vLLM)

```bash
swapgate compare --suite suite.json \
  --baseline "openai-compat:https://api.provider.com/v1|frontier-large" \
  --candidate "openai-compat:http://localhost:8000/v1|sarvam-30b" \
  --fail-under 0.9 --max-regression 0.05 \
  --out receipt.json --report report.md --sign
```

Key from `SWAPGATE_API_KEY`. The candidate needs no key when it runs on localhost.
