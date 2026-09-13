from pathlib import Path
import re


FRONTEND = Path(__file__).resolve().parents[1] / 'frontend' / 'src'


def _production_sources():
    return [
        path for path in FRONTEND.rglob('*.tsx')
        if not path.name.endswith('.test.tsx')
    ]


# A bare "#fragment" href never reaches the router: canonicalClientPath() returns None for
# anything starting with '#' (see client-routes.ts), so InternalLink renders a plain <a> for
# it anyway. Same-page anchors are therefore outside what this guard protects, and exempting
# them by shape is narrower than exempting a file — which is what the skip-link line below
# used to do, and what a Methodology link inside a translated sentence would have needed.
_ANCHOR = re.compile(r'<a(?=[\s>])[^>]*>')
# Two href shapes canonicalClientPath() rejects outright, so InternalLink renders a plain <a>
# for them anyway and routing them through it would change nothing:
#   - a bare "#fragment"   (client-routes.ts: returns None when href starts with '#')
#   - an absolute URL      (returns None for a foreign origin or a non-http(s) scheme)
# Both appear inside translated sentences, where the link has to be part of the message so a
# translator can move it. The realistic mistake -- a root-relative path like "/consultations"
# that should have been a client-side navigation -- is still caught.
# Residual gap: an absolute URL on our OWN origin would slip through. Nothing in the codebase
# writes one, and the guard below pins that path anchors keep failing.
_EXEMPT_HREF = re.compile(r'\bhref=(?:"|\'|\{`)(?:#|[a-z][a-z0-9+.-]*://)')


def _routable_raw_anchors(source):
    return [tag for tag in _ANCHOR.findall(source) if not _EXEMPT_HREF.search(tag)]


def test_production_pages_do_not_bypass_internal_link_navigation():
    violations = []
    for path in _production_sources():
        if path.name == 'internal-link.tsx':
            continue
        source = path.read_text(encoding='utf-8')
        if _routable_raw_anchors(source):
            violations.append(path.relative_to(FRONTEND).as_posix())

    assert violations == []


def test_the_anchor_guard_still_catches_a_routable_raw_anchor():
    """Guards the guard: the fragment exemption must not swallow a real violation."""
    assert _routable_raw_anchors('<a href="/consultations">x</a>') == ['<a href="/consultations">']
    assert _routable_raw_anchors('<a className="c" href="/admin">x</a>')
    assert _routable_raw_anchors('<a href="#methodology">x</a>') == []
    assert _routable_raw_anchors('<a href="https://creativecommons.org/x">x</a>') == []
    assert _routable_raw_anchors('<a href="/consultations" target="_blank">x</a>')  # still caught
    assert _routable_raw_anchors('<a className="skip-link" href="#main">x</a>') == []
    assert _routable_raw_anchors('<InternalLink href="/x" />') == []


def test_full_document_redirects_are_confined_to_server_navigation_boundary():
    violations = []
    for path in _production_sources():
        source = path.read_text(encoding='utf-8')
        if 'location.assign(' in source and path.name != 'external-redirect.tsx':
            violations.append(path.relative_to(FRONTEND).as_posix())

    assert violations == []
