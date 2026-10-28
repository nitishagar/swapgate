"""G5: site + packaging + Action metadata tests (offline, static)."""

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
DOCS = os.path.join(ROOT, "docs")

PAGES = ["index.html", "quickstart.html", "concepts.html", "cli.html", "india-pack.html",
         "hosting.html"]


def test_all_pages_and_css_exist():
    for page in PAGES + ["style.css"]:
        assert os.path.exists(os.path.join(DOCS, page)), page


def test_internal_links_resolve():
    for page in PAGES:
        with open(os.path.join(DOCS, page), encoding="utf-8") as fh:
            html = fh.read()
        for ref in re.findall(r'(?:href|src)="([^"#]+?)"', html):
            if ref.startswith(("http://", "https://", "mailto:")):
                continue
            target = os.path.normpath(os.path.join(DOCS, ref))
            assert os.path.exists(target), f"{page} -> {ref}"


def test_no_external_assets():
    """Pages must render offline: stylesheets, scripts, images are local."""
    for page in PAGES:
        with open(os.path.join(DOCS, page), encoding="utf-8") as fh:
            html = fh.read()
        for tag in re.findall(r'<(?:link|script|img)[^>]+>', html):
            for attr in re.findall(r'(?:href|src)="([^"]+)"', tag):
                assert not attr.startswith(("http://", "https://")), f"{page}: {tag}"


def test_report_indexed():
    """Every docs/reports page must be linked from index.html (fails if unwired)."""
    reports = os.path.join(DOCS, "reports")
    assert os.path.isdir(reports)
    with open(os.path.join(DOCS, "index.html"), encoding="utf-8") as fh:
        index = fh.read()
    pages = sorted(f for f in os.listdir(reports) if f.endswith(".html"))
    assert pages
    for page in pages:
        assert f"reports/{page}" in index, page


def test_every_page_links_home_and_has_title():
    for page in PAGES:
        with open(os.path.join(DOCS, page), encoding="utf-8") as fh:
            html = fh.read()
        assert "<title>" in html and "</title>" in html
        assert 'href="index.html"' in html


def test_action_metadata_shape():
    with open(os.path.join(ROOT, "action", "action.yml"), encoding="utf-8") as fh:
        text = fh.read()
    for required in ["name:", "description:", "inputs:", "runs:", "suite:",
                     "fail-under:", "max-regression:", "upload-artifact"]:
        assert required in text, required


def test_packaging_metadata_present():
    assert os.path.exists(os.path.join(ROOT, "LICENSE"))
    assert os.path.exists(os.path.join(ROOT, "README.md"))
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        text = fh.read()
    assert 'name = "swapgate"' in text
    assert "swapgate.cli:main" in text
    assert os.path.exists(os.path.join(ROOT, "packages", "swapgate-js", "package.json"))
