# Security review — SwapGate completeness plan (P4 hosted tier + diff cross-cutting)

Scope: `git diff 1cd9cf9..HEAD` in `swapgate/`. Method: adversarial read of every new
auth/input/crypto/file-I/O path with file:line evidence, plus secret sweeps of the diff.

## Important findings

### I1. Authenticated SSRF + operator provider-key exfil via caller-chosen provider URL (serve.py → runner.py)

- `src/swapgate/serve.py:139-143` — `_handle_compare` passes caller-controlled
  `body["baseline"]` / `body["candidate"]` straight into `parse_provider()`, which
  accepts `openai-compat:<base-url>|<model>` with an arbitrary URL.
- `src/swapgate/runner.py:70-87` (pre-existing, newly network-exposed by this diff) —
  `OpenAICompatProvider` reads the **server's** `SWAPGATE_API_KEY` env var
  (runner.py:73) and sends it as `Authorization: Bearer …` to that caller-chosen
  URL (runner.py:79-86), POSTing suite prompt content there.
- Any holder of a team key (a tenant) can therefore point baseline/candidate at an
  attacker server and harvest the operator's provider API key from the inbound
  Authorization header, and can make the server issue POSTs to arbitrary internal
  URLs (SSRF; `…/chat/completions` suffix, error text/timing oracle via the
  `provider_error` 500 at serve.py:155, truncated to 200 chars).
- Partial mitigations already present: localhost-only bind (serve.py:271) and
  operator-issued keys (no self-serve signup) narrow who can reach this, but the
  hosted tier is explicitly multi-tenant, so tenants are the threat actor here.

Fix (any one): restrict hosted providers to `mock:*` in `_handle_compare`; or
allowlist `openai-compat` base URLs via env; or never forward the server-side
`SWAPGATE_API_KEY` for caller-supplied URLs (require per-request key or none).

## Nits (5 max)

1. Nit — `src/swapgate/billing.py:46-61`: `record_event` is SELECT-then-INSERT, so two
   concurrent retries of the same event can both return True. Harmless (record-only
   ledger, UNIQUE PK prevents double rows, both callers get 200), but not strictly
   insert-first under race.
2. Nit — `src/swapgate/serve.py:269-274`: no socket/read timeout and unbounded
   `ThreadingHTTPServer` threads; a slow client or an evil-regex suite (attacker
   controls rubric `regex` patterns via the inline suite) can pin threads/CPU.
   Authenticated + localhost-only, so low severity. Consider `server.timeout` and a
   regex-complexity cap or judge timeout.
3. Nit — `src/swapgate/serve.py:178-186`: `_owned_run`/`_handle_list_runs` load ALL
   history rows then filter by `team_id` in Python. No leak (filter is correct, NULL
   rows never served), but unbounded memory/response growth per team.
4. Nit — `src/swapgate/serve.py:100-107`: `_dispatch` catches only `ApiError` (plus
   `BrokenPipeError`); e.g. `sqlite3.OperationalError` on lock contention drops the
   connection with no JSON body (traceback goes to server stderr, not the client —
   no leak, just an availability/UX wart). Consider a catch-all → 500 envelope.
5. Nit — redaction boundary (adjacent, pre-existing files untouched by this diff):
   `src/swapgate/redact.py:60-66` redacts only `messages`/`output`, so
   `tool_calls[].args`/`usage`/`metadata` persist verbatim through `capture`; the new
   `src/swapgate/secmcp_emit.py:22-55` producer likewise emits caller-supplied
   `args`/`result`/messages unredacted. No new in-diff bypass, but anyone relying on
   `--redact` for tool-arg secrets gets none.

Further minor notes (count: 4, not individually filed): Dockerfile `EXPOSE 8000` vs
127.0.0.1 bind mismatch (fail-closed, but the published `-p 8000:8000` recipe can't
work as written); `receipt.py:74` uses `!=` (not `compare_digest`) for the content-hash
string compare — unexploitable without the HMAC key, defense-in-depth only;
`teams.py:30-39` `issue_key` doesn't check the team exists (orphan keys for bogus ids,
operator-only path); Stripe events with missing `id` collapse to event_key `"None"`
(serve.py:227, unreachable without a valid signature).

## Checked and clean (with evidence)

- Team-key auth: sha256-hashed storage, `secrets.token_urlsafe(32)` entropy,
  `hmac.compare_digest` scan, revoked excluded (`teams.py:14-16,33,42-50`); strict
  `Bearer` scheme check, 401 on missing/invalid (`serve.py:74-82`); only intended
  unauthenticated routes are the SDK-verified webhooks (`serve.py:84-99`).
- Team isolation: reads filter by caller `team_id`, foreign/NULL → 404
  (`serve.py:173-196`); covered by `tests/test_serve.py:113-136`.
- Route safety: ids `int()`-parsed before lookup — no traversal (`serve.py:173-181`);
  LLM judge unreachable remotely (no `fixtures_path` passed, `serve.py:136` + `judges/__init__.py:22-33` → 400), so no remote local-file read.
- Body limits: `MAX_BODY_BYTES` 1 MB → 413, invalid Content-Length → 400
  (`serve.py:65-72`); HTTP/1.0 default, no keep-alive poisoning.
- Error hygiene: webhook failures return exception *type names* only, never secrets
  (`serve.py:222,251`); `check_test_mode` echoes config names, not values
  (`billing.py:19-23`); provider errors truncate to 200 chars and can't contain the
  server key (header-only) — except via I1's exfil channel.
- Billing: real `stripe.Webhook.construct_event` with 300 s tolerance
  (`billing.py:26-31`); Razorpay verifies over raw UTF-8 text (`billing.py:34-39`,
  `serve.py:244-249`); Stripe `livemode:false` enforced (`serve.py:224-225`);
  Razorpay test-account allowlist enforced (`serve.py:256-259`); live-shaped secrets
  refused (`billing.py:19-23`); secrets env-only, never logged; dedup → 200 no-op
  (`billing.py:42-61`); record-only ledger — no amount/currency handling and no
  charge-creating path anywhere in the diff.
- Receipt HMAC: `compare_digest` on the signature (`receipt.py:70-77`); key file
  created 0o600 (`receipt.py:43-52`).
- SQLite: all queries parameterized; the single f-string interpolates a constant int
  (`history.py:54`); per-op connections, WAL, 5 s busy timeout, `BEGIN IMMEDIATE`
  claim with TTL reap closes the check-then-act race (`history.py:49-62,130-157`);
  atomic schedule save via tmp+`os.replace` (`schedule.py:44-48`).
- Subprocess: all `subprocess.run` call sites use argv lists, no `shell=True`
  (`tests/test_cli.py:160`, `tests/test_diet.py:37`, `tests/e2e/*`, `examples/swap-reports/generate.py:43`).
- Secrets sweep: diff-wide grep for private keys, `AKIA`, `ghp_/gho_`, `sk-`, `xox-`,
  passwords, live patterns — hits are only obvious dummies/placeholders
  (`whsec_smoke`, `rzpay_smoke`, `whsec_testbilling1`, `rzpay_testsecret1`, `whsec_...`,
  `acc_...` in CI/docs/tests) plus the `LIVE_PATTERNS` denylist itself.
- Publish workflow uses PyPI trusted publishing + npm provenance, minimal
  permissions (`.github/workflows/publish.yml`).
- Frontend XSS: static docs only — `docs/hosting.html` is static markup whose only
  script is a localStorage theme toggle; no user input is interpolated. Confirmed.

## Verdict

VERDICT: MINOR-FAIL
