# SwapGate GitHub Action

Fails the PR when a candidate model regresses on your eval suite.

```yaml
- uses: nitishagar/swapgate@v0
  with:
    suite: evals/suite.json
    baseline: mock:parity
    candidate: openai-compat:https://openrouter.ai/api/v1|qwen/qwen-3-32b
    fail-under: '0.95'
    max-regression: '0.02'
```

Live providers read the key from `SWAPGATE_API_KEY` — set it as an Actions secret:

```yaml
env:
  SWAPGATE_API_KEY: ${{ secrets.SWAPGATE_API_KEY }}
```

Outputs: `passed` (`true`/`false`), `receipt` (path to the signed receipt JSON,
also uploaded as the `swapgate-receipt` artifact). A Markdown report is appended
to the job summary either way.
