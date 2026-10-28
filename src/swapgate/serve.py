"""Single-instance hosted API (stdlib http.server).

Routes (all JSON; errors as {error:{code,message}}):
  POST /v1/compare                    (auth; inline approved suite)
  GET  /v1/runs                       (caller's team only)
  GET  /v1/runs/:id                   (404 unless caller's team)
  GET  /v1/receipts/:id               (404 unless caller's team)
  POST /v1/billing/stripe/webhook     (no team auth; SDK signature)
  POST /v1/billing/razorpay/webhook   (no team auth; SDK signature)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from . import history, teams
from .compare import compare
from .evals import EvalSuite
from .judges import get_judge
from .receipt import build_receipt_body, load_or_create_key, sign_receipt
from .runner import OpenAICompatProvider, Provider, parse_provider

MAX_BODY_BYTES = 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


def _valid_threshold(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0.0 <= value <= 1.0)


def _hosted_provider(spec: Any) -> Provider:
    """Parse a tenant-supplied provider without the operator's API key.

    `openai-compat:<url>|<model>` accepts an arbitrary URL, so forwarding the
    server-side `SWAPGATE_API_KEY` would let any team key harvest it (plus
    credentialed SSRF). Hosted live providers run keyless; operators needing
    authenticated live replays use the CLI or scheduler instead.
    """
    provider = parse_provider(spec)
    if isinstance(provider, OpenAICompatProvider):
        provider.api_key = ""
    return provider


class Handler(BaseHTTPRequestHandler):
    server_version = "SwapGate/0.2"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter than stdlib default
        pass

    @property
    def ctx(self) -> dict[str, Any]:
        return self.server.context  # type: ignore[attr-defined]

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, err: ApiError) -> None:
        self._send(err.status, {"error": {"code": err.code, "message": str(err)}})

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(400, "bad_request", "invalid Content-Length")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, "body_too_large", f"body cap is {MAX_BODY_BYTES} bytes")
        return self.rfile.read(max(length, 0))

    def _team(self) -> int:
        header = self.headers.get("Authorization", "")
        scheme, _, key = header.partition(" ")
        if scheme != "Bearer" or not key:
            raise ApiError(401, "unauthorized", "missing Bearer key")
        team_id = teams.resolve_key(self.ctx["history_path"], key)
        if team_id is None:
            raise ApiError(401, "unauthorized", "invalid or revoked key")
        return team_id

    def _route(self, method: str, path: str) -> Callable[[], None]:
        routes: dict[tuple[str, str], Callable[[], None]] = {
            ("POST", "/v1/compare"): self._handle_compare,
            ("GET", "/v1/runs"): self._handle_list_runs,
            ("POST", "/v1/billing/stripe/webhook"): self._handle_stripe,
            ("POST", "/v1/billing/razorpay/webhook"): self._handle_razorpay,
        }
        handler = routes.get((method, path))
        if handler is not None:
            return handler
        if method == "GET" and path.startswith("/v1/runs/"):
            return lambda: self._handle_get_run(path[len("/v1/runs/"):])
        if method == "GET" and path.startswith("/v1/receipts/"):
            return lambda: self._handle_get_receipt(path[len("/v1/receipts/"):])
        raise ApiError(404, "not_found", f"no route {method} {path}")

    def _dispatch(self, method: str) -> None:
        try:
            path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
            self._route(method, path)()
        except ApiError as err:
            self._send_error(err)
        except BrokenPipeError:
            pass

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    # ---- compare ----

    def _handle_compare(self) -> None:
        team_id = self._team()
        try:
            body = json.loads(self._read_body() or b"null")
        except (json.JSONDecodeError, ValueError):
            raise ApiError(400, "bad_request", "malformed JSON")
        if not isinstance(body, dict) or not isinstance(body.get("suite"), dict):
            raise ApiError(400, "bad_request", "need an inline suite object")
        try:
            suite = EvalSuite.from_dict(body["suite"])
        except (TypeError, KeyError, ValueError) as exc:
            raise ApiError(400, "bad_request", f"bad suite: {exc}")
        if not suite.metadata.get("approved"):
            raise ApiError(400, "unapproved_suite", "suite lacks metadata.approved")
        fail_under = body.get("fail_under", 0.0)
        max_regression = body.get("max_regression", 1.0)
        if not _valid_threshold(fail_under) or not _valid_threshold(max_regression):
            raise ApiError(400, "bad_request", "thresholds must be finite numbers in [0,1]")
        try:
            judge = get_judge(body.get("judge", "deterministic"))
        except ValueError:
            raise ApiError(400, "bad_judge", f"unknown judge: {body.get('judge')}")
        try:
            baseline = _hosted_provider(body.get("baseline", "mock:parity"))
            candidate = _hosted_provider(body.get("candidate", "mock:parity"))
        except ValueError as exc:
            raise ApiError(400, "bad_provider", str(exc))
        try:
            result = compare(suite, baseline, candidate, judge,
                             fail_under=fail_under, max_regression=max_regression)
        except Exception as exc:  # noqa: BLE001 — provider/judge failures → 500 + row
            history.append_run(self.ctx["history_path"], {
                "suite": suite.name, "baseline": baseline.label,
                "candidate": candidate.label, "judge": getattr(judge, "name", "?"),
                "fail_under": fail_under, "max_regression": max_regression,
                "receipt": None, "error": f"{type(exc).__name__}: {exc}"[:500],
                "team_id": team_id,
            })
            raise ApiError(500, "provider_error", f"{type(exc).__name__}: {exc}"[:200])
        summary = result.summary()
        receipt = sign_receipt(
            build_receipt_body(summary, [c.to_dict() for c in result.cases]),
            self.ctx["key"])
        row_id = history.append_run(self.ctx["history_path"], {
            "suite": suite.name, "baseline": summary["baseline"],
            "candidate": summary["candidate"], "judge": summary["judge"],
            "fail_under": fail_under, "max_regression": max_regression,
            "passed": summary["passed"],
            "baseline_pass_rate": summary["baseline_pass_rate"],
            "candidate_pass_rate": summary["candidate_pass_rate"],
            "receipt": receipt, "error": None, "team_id": team_id,
        })
        self._send(200, {"run_id": row_id, "receipt": receipt})

    # ---- reads (team-scoped; NULL-team rows never served) ----

    def _owned_run(self, raw_id: str, team_id: int) -> dict[str, Any]:
        try:
            want = int(raw_id)
        except ValueError:
            raise ApiError(404, "not_found", "no such run")
        for row in history.list_runs(self.ctx["history_path"]):
            if row["id"] == want and row.get("team_id") == team_id:
                return row
        raise ApiError(404, "not_found", "no such run")

    def _handle_list_runs(self) -> None:
        team_id = self._team()
        rows = [r for r in history.list_runs(self.ctx["history_path"])
                if r.get("team_id") == team_id]
        self._send(200, {"runs": rows})

    def _handle_get_run(self, raw_id: str) -> None:
        self._send(200, {"run": self._owned_run(raw_id, self._team())})

    def _handle_get_receipt(self, raw_id: str) -> None:
        row = self._owned_run(raw_id, self._team())
        if not row.get("receipt"):
            raise ApiError(404, "not_found", "run has no receipt")
        self._send(200, {"receipt": row["receipt"]})

    # ---- billing webhooks (SDK-verified, record-only) ----

    def _billing_config(self) -> dict[str, str]:
        return {
            "STRIPE_WEBHOOK_SECRET": os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
            "RAZORPAY_WEBHOOK_SECRET": os.environ.get("RAZORPAY_WEBHOOK_SECRET", ""),
            "RAZORPAY_TEST_ACCOUNTS": os.environ.get("RAZORPAY_TEST_ACCOUNTS", ""),
        }

    def _handle_stripe(self) -> None:
        from . import billing

        secret = self._billing_config()["STRIPE_WEBHOOK_SECRET"]
        if not secret:
            raise ApiError(500, "billing_unconfigured", "STRIPE_WEBHOOK_SECRET not set")
        try:
            billing.check_test_mode({"STRIPE_WEBHOOK_SECRET": secret})
        except ValueError as exc:
            raise ApiError(500, "live_credentials", str(exc))
        raw = self._read_body()
        try:
            event = billing.verify_stripe(
                raw, self.headers.get("Stripe-Signature", ""), secret)
        except Exception as exc:  # noqa: BLE001 — SDK raises on bad signatures
            raise ApiError(400, "bad_signature", f"stripe: {type(exc).__name__}")
        evt = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        if evt.get("livemode") is not False:
            raise ApiError(400, "live_mode", "test-mode only (livemode must be false)")
        billing.record_event(self.ctx["history_path"], "stripe",
                             str(evt.get("id")), raw.decode("utf-8", "replace"))
        self._send(200, {"ok": True})

    def _handle_razorpay(self) -> None:
        from . import billing

        secret = self._billing_config()["RAZORPAY_WEBHOOK_SECRET"]
        if not secret:
            raise ApiError(500, "billing_unconfigured", "RAZORPAY_WEBHOOK_SECRET not set")
        try:
            billing.check_test_mode({"RAZORPAY_WEBHOOK_SECRET": secret,
                                     "RAZORPAY_TEST_ACCOUNTS":
                                     self._billing_config()["RAZORPAY_TEST_ACCOUNTS"]})
        except ValueError as exc:
            raise ApiError(500, "live_credentials", str(exc))
        raw = self._read_body()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ApiError(400, "bad_request", "body must be UTF-8")
        try:
            billing.verify_razorpay(
                text, self.headers.get("X-Razorpay-Signature", ""), secret)
        except Exception as exc:  # noqa: BLE001 — SDK raises on bad signatures
            raise ApiError(400, "bad_signature", f"razorpay: {type(exc).__name__}")
        try:
            body = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            raise ApiError(400, "bad_request", "malformed JSON")
        allowed = {a.strip() for a in
                   self._billing_config()["RAZORPAY_TEST_ACCOUNTS"].split(",") if a.strip()}
        if not allowed or body.get("account_id") not in allowed:
            raise ApiError(400, "unknown_account", "account not in test allowlist")
        try:
            pay_id = body["payload"]["payment"]["entity"]["id"]
            event_key = f"{body.get('event')}:{pay_id}"
        except (KeyError, TypeError):
            event_key = hashlib.sha256(raw).hexdigest()
        billing.record_event(self.ctx["history_path"], "razorpay", event_key, text)
        self._send(200, {"ok": True})


def create_server(port: int, history_path: str, key: bytes) -> ThreadingHTTPServer:
    history.init_db(history_path)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.context = {"history_path": history_path, "key": key}  # type: ignore[attr-defined]
    server.daemon_threads = True
    return server


def serve_forever(port: int, history_path: str, key: bytes) -> None:
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(0))
    server = create_server(port, history_path, key)
    try:
        server.serve_forever()
    finally:
        server.server_close()
