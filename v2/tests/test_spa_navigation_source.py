from pathlib import Path
import re


FRONTEND = Path(__file__).resolve().parents[1] / 'frontend' / 'src'


def _production_sources():
    return [
        path for path in FRONTEND.rglob('*.tsx')
        if not path.name.endswith('.test.tsx')
    ]


def test_production_pages_do_not_bypass_internal_link_navigation():
    violations = []
    for path in _production_sources():
        if path.name == 'internal-link.tsx':
            continue
        source = path.read_text(encoding='utf-8')
        raw_anchors = len(re.findall(r'<a(?:\s|>)', source))
        if path.name == 'app.tsx':
            raw_anchors -= source.count('<a className="skip-link" href="#main">')
        if raw_anchors:
            violations.append(path.relative_to(FRONTEND).as_posix())

    assert violations == []


def test_full_document_redirects_are_confined_to_server_navigation_boundary():
    violations = []
    for path in _production_sources():
        source = path.read_text(encoding='utf-8')
        if 'location.assign(' in source and path.name != 'external-redirect.tsx':
            violations.append(path.relative_to(FRONTEND).as_posix())

    assert violations == []
