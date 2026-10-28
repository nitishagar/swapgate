"""SwapGate CLI: capture | build-evals | compare | report | verify | serve-mcp."""

from __future__ import annotations

import argparse
import json
import os
import sys

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_GATE_FAIL = 2

from . import __version__
from .compare import compare
from .evals import (
    ApprovalRequiredError,
    build_suite,
    finalize_pending,
    load_suite,
    pending_path_for,
    save_suite,
)
from .ingest import parse_litellm, parse_otel_span, parse_secmcp
from .judges.deterministic import DeterministicJudge
from .judges.llm import FixtureCompleter, LLMJudge
from .judges.typed import TypedJudge
from .receipt import (
    build_receipt_body,
    load_or_create_key,
    load_receipt,
    save_receipt,
    sign_receipt,
    verify_receipt,
)
from .redact import DEFAULT_KEY as REDACT_KEY
from .redact import Redactor
from .report import to_html, to_markdown
from .runner import parse_provider
from .traces import TraceEvent, read_jsonl, read_jsonl_tolerant, write_jsonl

PARSERS = {"litellm": parse_litellm, "otel": parse_otel_span, "secmcp": parse_secmcp}


def cmd_capture(args: argparse.Namespace) -> int:
    parser = PARSERS[args.source]
    rows, corrupt = read_jsonl_tolerant(args.input)
    events: list[TraceEvent] = []
    skipped = corrupt
    for row in rows:
        event = parser(row)
        if event is None:
            skipped += 1
        else:
            events.append(event)
    if args.redact:
        redactor = Redactor(profile=args.redact, key=REDACT_KEY)
        events = [redactor.redact_event(e) for e in events]
    write_jsonl(args.output, [e.to_dict() for e in events])
    print(f"captured {len(events)} events -> {args.output} (skipped {skipped} unparsable)")
    return EXIT_OK


def cmd_build_evals(args: argparse.Namespace) -> int:
    if args.approve:
        pending = pending_path_for(args.output)
        if not os.path.exists(pending):
            print(f"error: no pending suite at {pending}; run without --approve first", file=sys.stderr)
            return EXIT_ERROR
        suite = load_suite(pending)
        save_suite(suite, args.output)
        print(f"approved {len(suite.cases)} cases -> {args.output}")
        return EXIT_OK
    rows = read_jsonl(args.input)
    events = [TraceEvent.from_dict(r) for r in rows]
    completer = None
    if args.rubrics == "llm":
        if args.rubrics_fixtures:
            with open(args.rubrics_fixtures, encoding="utf-8") as fh:
                completer = FixtureCompleter(json.load(fh))
        else:
            base = os.environ.get("SWAPGATE_BASE_URL", "")
            model = os.environ.get("SWAPGATE_MODEL", "")
            if not base or not model:
                print("error: --rubrics llm needs --rubrics-fixtures or "
                      "SWAPGATE_BASE_URL/SWAPGATE_MODEL", file=sys.stderr)
                return EXIT_ERROR
            from .rubrics_llm import ProviderCompleter
            completer = ProviderCompleter(parse_provider(f"openai-compat:{base}|{model}"))
    suite = build_suite(args.name, events, max_clusters=args.clusters,
                        rubric_source=args.rubrics, rubric_completer=completer)
    if args.india_pack:
        from .india import apply_pack
        suite = apply_pack(suite)
    pending = pending_path_for(args.output)
    save_suite(suite, pending)
    print(f"wrote {len(suite.cases)} cases -> {pending}")
    print("REVIEW the rubrics, then re-run with --approve to finalise.")
    return EXIT_OK


def _judge_for(args: argparse.Namespace):  # noqa: ANN202 (tiny CLI factory)
    if args.judge == "deterministic":
        return DeterministicJudge()
    if args.judge == "typed":
        return TypedJudge()
    if args.judge == "llm":
        if not args.judge_fixtures:
            print("error: --judge llm needs --judge-fixtures (offline) or a live completer", file=sys.stderr)
            raise SystemExit(EXIT_ERROR)
        with open(args.judge_fixtures, encoding="utf-8") as fh:
            return LLMJudge(FixtureCompleter(json.load(fh)))
    raise SystemExit(f"unknown judge: {args.judge}")


def cmd_compare(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    judge = _judge_for(args)
    baseline = parse_provider(args.baseline)
    candidate = parse_provider(args.candidate)
    result = compare(
        suite, baseline, candidate, judge,
        fail_under=args.fail_under, max_regression=args.max_regression,
    )
    from .receipt import DEFAULT_KEY_PATH as _default_key
    key_path = args.key or (_default_key if args.sign else "")
    key = load_or_create_key(key_path) if key_path else None
    body = build_receipt_body(result.summary(), [c.to_dict() for c in result.cases])
    receipt = sign_receipt(body, key) if key else {**body, "content_hash": "", "signature": "", "signature_scheme": "none"}
    if args.output:
        save_receipt(receipt, args.output)
    if args.report:
        text = to_markdown(receipt) if args.report.endswith(".md") else to_html(receipt)
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    s = result.summary()
    print(f"baseline {s['baseline_pass_rate']} candidate {s['candidate_pass_rate']} "
          f"gap {s['regression_gap']} -> {'PASS' if s['passed'] else 'FAIL'}")
    return EXIT_OK if s["passed"] else EXIT_GATE_FAIL


def cmd_report(args: argparse.Namespace) -> int:
    receipt = load_receipt(args.receipt)
    text = to_markdown(receipt) if args.format == "md" else to_html(receipt)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    receipt = load_receipt(args.receipt)
    with open(args.key, "rb") as fh:
        key = fh.read().strip()
    ok = verify_receipt(receipt, key)
    print("receipt VALID" if ok else "receipt INVALID")
    return EXIT_OK if ok else EXIT_GATE_FAIL


def cmd_serve_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import serve
    serve()
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swapgate", description="Model-swap eval gate.")
    parser.add_argument("--version", action="version", version=f"swapgate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("capture", help="ingest raw traces into canonical events")
    p.add_argument("--from", dest="source", choices=["litellm", "otel", "secmcp"], required=True)
    p.add_argument("--in", dest="input", required=True)
    p.add_argument("--out", dest="output", required=True)
    p.add_argument("--redact", choices=["default", "india", "dpdp-strict"], default="")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("build-evals", help="cluster events into an eval suite (approval-gated)")
    p.add_argument("--in", dest="input", default="",
                   help="events JSONL (not needed with --approve)")
    p.add_argument("--out", dest="output", required=True)
    p.add_argument("--name", default="suite")
    p.add_argument("--clusters", type=int, default=8)
    p.add_argument("--india-pack", action="store_true")
    p.add_argument("--rubrics", choices=["heuristic", "llm"], default="heuristic")
    p.add_argument("--rubrics-fixtures", default="")
    p.add_argument("--approve", action="store_true")
    p.set_defaults(func=cmd_build_evals)

    p = sub.add_parser("compare", help="replay suite on baseline vs candidate; fail on regression")
    p.add_argument("--suite", required=True)
    p.add_argument("--baseline", default="mock:parity")
    p.add_argument("--candidate", default="mock:parity")
    p.add_argument("--judge", choices=["deterministic", "typed", "llm"], default="deterministic")
    p.add_argument("--judge-fixtures", default="")
    p.add_argument("--out", dest="output", default="")
    p.add_argument("--report", default="")
    p.add_argument("--fail-under", type=float, default=0.0)
    p.add_argument("--max-regression", type=float, default=1.0)
    p.add_argument("--key", default="", help="sign with this key file (created if missing)")
    p.add_argument("--sign", action="store_true", help="sign with the default key ~/.swapgate/key")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("report", help="render a receipt as Markdown or HTML")
    p.add_argument("--receipt", required=True)
    p.add_argument("--format", choices=["md", "html"], default="md")
    p.add_argument("--out", dest="output", default="")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("verify", help="verify a signed receipt")
    p.add_argument("--receipt", required=True)
    p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("serve-mcp", help="run the stdio MCP server")
    p.set_defaults(func=cmd_serve_mcp)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "command", "") == "compare" and args.sign and not args.key:
        from .receipt import DEFAULT_KEY_PATH
        args.key = DEFAULT_KEY_PATH
    try:
        return int(args.func(args))
    except ApprovalRequiredError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc.filename}", file=sys.stderr)
        return EXIT_ERROR
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
