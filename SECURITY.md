# Security

SwapGate handles production LLM traces, which routinely contain personal data.

- Redact before storage (`--redact india` or `--redact dpdp-strict`); retain briefly.
- Receipt keys (`~/.swapgate/key`, mode 0600) never leave your machine.
- HMAC receipts are tamper-evident, not third-party-verifiable.

To report a vulnerability, open a private security advisory on GitHub or email
the maintainer. Do not file public issues with exploit details or real trace data.
