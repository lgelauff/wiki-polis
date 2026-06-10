"""Inline-<script> JS syntax gate — rides the pytest job in CI.

Vendored from the agent-tooling toolkit's scripts/check_inline_js.py (canonical:
github.com/lgelauff/wikimedia-coding-agent-lessons). Catches the dead-<script>
class — e.g. a smart/curly quote used as a JS string delimiter — that renders
fine and passes every server-side test but never executes in the browser (the
PR #174 arguments-tab blocker). Skips if `node` is absent locally; CI installs it.
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile

import pytest

TEMPLATES = os.path.join(os.path.dirname(__file__), os.pardir, "templates")
_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL | re.IGNORECASE)


def _is_js(attrs):
    if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE):
        return False
    m = re.search(r'type\s*=\s*["\']([^"\']*)["\']', attrs, re.IGNORECASE)
    if m:
        return m.group(1).lower() in ("", "text/javascript", "module", "application/javascript")
    return True


def _strip_jinja(s):
    s = re.sub(r"\{#.*?#\}", "", s, flags=re.DOTALL)
    s = re.sub(r"\{%.*?%\}", "", s, flags=re.DOTALL)
    return re.sub(r"\{\{.*?\}\}", "0", s, flags=re.DOTALL)


def _scripts(html):
    for m in _SCRIPT.finditer(html):
        if m.group(2).strip() and _is_js(m.group(1)):
            yield html.count("\n", 0, m.start(2)) + 1, m.group(2)


@pytest.mark.skipif(not shutil.which("node"), reason="node not available")
@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(TEMPLATES, "*.html"))))
def test_inline_js_parses(path):
    html = open(path, encoding="utf-8").read()
    for line, body in _scripts(html):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(_strip_jinja(body))
            tmp = fh.name
        try:
            r = subprocess.run(["node", "--check", tmp],
                               capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(tmp)
        msg = (r.stderr.strip().splitlines() or ["parse error"])[0] if r.returncode else ""
        assert r.returncode == 0, \
            f"{os.path.basename(path)} <script> at line {line}: {msg}"
