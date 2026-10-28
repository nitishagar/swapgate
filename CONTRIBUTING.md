# Contributing

## Setup

```bash
git clone https://github.com/nitishagar/swapgate.git
cd swapgate
uv venv && uv pip install -e '.[dev]'
```

## Gates

Every change must keep every gate green, offline:

```bash
pytest                                  # G0-G5, no keys/network
SWAPGATE_LIVE=1 pytest -m live          # L, needs SWAPGATE_BASE_URL/MODEL
npm --prefix packages/swapgate-js test  # TS SDK
```

New behaviour needs a focused test in `tests/` first; golden changes
(`tests/golden/`) must be deliberate and explained in the PR.

## Rules

- Core stays stdlib-only. New runtime dependencies need justification.
- No network or keys in the default test path; live tests stay behind `SWAPGATE_LIVE=1`.
- Never commit trace data with real PII — fixtures use synthetic identities.
- Commits carry no co-author trailers.
