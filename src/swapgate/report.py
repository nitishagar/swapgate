"""Swap receipt reports: Markdown and self-contained HTML."""

from __future__ import annotations

import html
from typing import Any

_HTML_CSS = """
:root{color-scheme:dark;--bg:#161d27;--bg-deep:#0d1116;--panel:#212730;
--line:#495059;--text:#ebe7e4;--muted:#9fa4ab;--accent:#b86b52;
--pass:#5db87a;--fail:#e8704f}
body{background:var(--bg-deep);color:var(--text);font-family:Georgia,'Times New Roman',serif;
margin:0;padding:2rem 1rem}
main{max-width:56rem;margin:0 auto}
h1{font-size:1.6rem}h1 .verdict-pass{color:var(--pass)}h1 .verdict-fail{color:var(--fail)}
table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.9rem}
th,td{border:1px solid var(--line);padding:.45rem .6rem;text-align:left}
th{background:var(--panel)}td.mono,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem}
.muted{color:var(--muted)}.badge{display:inline-block;padding:.1rem .5rem;border-radius:.4rem;
font-family:ui-monospace,Menlo,monospace;font-size:.78rem}
.badge.pass{background:#1d3a28;color:var(--pass)}.badge.fail{background:#3a241d;color:var(--fail)}
.badge.review{background:#3a3320;color:#e8993a}
details{background:var(--bg);border:1px solid var(--line);border-radius:.4rem;
padding:.5rem .8rem;margin:.4rem 0}
summary{cursor:pointer;font-family:ui-monospace,Menlo,monospace;font-size:.85rem}
pre{white-space:pre-wrap;word-break:break-word;font-size:.78rem;color:var(--muted)}
a{color:var(--accent)}
"""


def _fence(text: str) -> str:
    """Neutralize fence runs so interpolated outputs cannot break code blocks."""
    return text.replace("```", "´´´")


def to_markdown(receipt: dict[str, Any]) -> str:
    s = receipt.get("summary", {})
    verdict = "PASS" if s.get("passed") else "FAIL"
    lines = [
        f"# Swap receipt: {verdict}",
        "",
        f"Suite `{s.get('suite')}` v{s.get('suite_version')} — "
        f"{s.get('n_cases')} cases, judge `{s.get('judge')}`.",
        "",
        f"- Baseline: `{s.get('baseline')}` pass rate **{s.get('baseline_pass_rate')}**",
        f"- Candidate: `{s.get('candidate')}` pass rate **{s.get('candidate_pass_rate')}**",
        f"- Regression gap: **{s.get('regression_gap')}** "
        f"(floor `{s.get('fail_under')}`, max gap `{s.get('max_regression')}`)",
        f"- Issued: {receipt.get('issued_at')}",
        f"- Content hash: `{receipt.get('content_hash')}`",
        "",
        "## Cases",
        "",
        "| case | baseline | candidate | regressed |",
        "|---|---|---|---|",
    ]
    for case in receipt.get("cases", []):
        b = "pass" if case.get("baseline_verdict", {}).get("passed") else "fail"
        c = "pass" if case.get("candidate_verdict", {}).get("passed") else "fail"
        r = "yes" if case.get("regressed") else "no"
        lines.append(f"| `{case.get('case_id')}` | {b} | {c} | {r} |")
    regressed = [c for c in receipt.get("cases", []) if c.get("regressed")]
    if regressed:
        lines += ["", "## Regressed cases", ""]
        for case in regressed:
            lines.append(f"### `{case.get('case_id')}`")
            lines.append("")
            lines.append("Baseline said:")
            lines.append("")
            lines.append(f"```\n{_fence(str(case.get('baseline_output', '')))}\n```")
            lines.append("Candidate said:")
            lines.append("")
            lines.append(f"```\n{_fence(str(case.get('candidate_output', '')))}\n```")
    lines += ["", f"_Verify: `swapgate verify --receipt receipt.json` ({receipt.get('signature_scheme')})_"]
    return "\n".join(lines) + "\n"


def _badge(label: str) -> str:
    cls = {"pass": "pass", "fail": "fail"}.get(label, "review")
    return f'<span class="badge {cls}">{html.escape(label)}</span>'


def to_html(receipt: dict[str, Any]) -> str:
    s = receipt.get("summary", {})
    verdict = "PASS" if s.get("passed") else "FAIL"
    vcls = "verdict-pass" if s.get("passed") else "verdict-fail"
    rows = []
    for case in receipt.get("cases", []):
        b = case.get("baseline_verdict", {})
        c = case.get("candidate_verdict", {})
        rows.append(
            "<tr><td class='mono'>" + html.escape(str(case.get("case_id"))) + "</td>"
            f"<td>{_badge(b.get('label', 'pass' if b.get('passed') else 'fail'))}</td>"
            f"<td>{_badge(c.get('label', 'pass' if c.get('passed') else 'fail'))}</td>"
            f"<td>{'yes' if case.get('regressed') else 'no'}</td></tr>"
        )
    details = []
    for case in receipt.get("cases", []):
        if not case.get("regressed"):
            continue
        details.append(
            "<details><summary>" + html.escape(str(case.get("case_id"))) + " — regressed</summary>"
            "<p class='muted'>Baseline:</p><pre>" + html.escape(str(case.get("baseline_output", ""))) + "</pre>"
            "<p class='muted'>Candidate:</p><pre>" + html.escape(str(case.get("candidate_output", ""))) + "</pre>"
            "</details>"
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Swap receipt: {verdict} — {html.escape(str(s.get('suite')))}</title>
<style>{_HTML_CSS}</style></head>
<body><main>
<h1>Swap receipt: <span class="{vcls}">{verdict}</span></h1>
<p class="muted">Suite <span class="mono">{html.escape(str(s.get('suite')))} v{html.escape(str(s.get('suite_version')))}</span>
— {html.escape(str(s.get('n_cases')))} cases, judge <span class="mono">{html.escape(str(s.get('judge')))}</span></p>
<table><tr><th></th><th>Model</th><th>Pass rate</th></tr>
<tr><td>Baseline</td><td class="mono">{html.escape(str(s.get('baseline')))}</td><td>{html.escape(str(s.get('baseline_pass_rate')))}</td></tr>
<tr><td>Candidate</td><td class="mono">{html.escape(str(s.get('candidate')))}</td><td>{html.escape(str(s.get('candidate_pass_rate')))}</td></tr>
</table>
<p>Regression gap <strong>{html.escape(str(s.get('regression_gap')))}</strong>
(floor {html.escape(str(s.get('fail_under')))}, max gap {html.escape(str(s.get('max_regression')))}).
Issued {html.escape(str(receipt.get('issued_at')))}.</p>
<p class="mono muted">hash {html.escape(str(receipt.get('content_hash')))} · {html.escape(str(receipt.get('signature_scheme')))}</p>
<h2>Cases</h2>
<table><tr><th>case</th><th>baseline</th><th>candidate</th><th>regressed</th></tr>
{''.join(rows)}</table>
{''.join(details)}
</main></body></html>
"""
