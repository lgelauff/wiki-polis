"""Unit tests for the i18n message loader/resolver (v2/i18n.py)."""

import json

import pytest
from flask import g as flask_g

import i18n


def _setup(tmp_path, messages):
    d = tmp_path / 'i18n'
    d.mkdir()
    for code, msgs in messages.items():
        (d / f'{code}.json').write_text(json.dumps(msgs), encoding='utf-8')
    i18n.load(str(d))
    return d


@pytest.fixture(autouse=True)
def _real_messages_around_each_test():
    # Unit tests below load a temp message dir; ensure the real i18n/ is loaded before AND
    # after each test so the integration tests (and other test files that render templates)
    # always see the real messages via the shared module state.
    i18n.load()
    yield
    i18n.load()


def test_lookup_and_english_fallback(tmp_path):
    _setup(tmp_path, {
        'en': {'@metadata': {'authors': []}, 'greet': 'Hello', 'only-en': 'Only'},
        'fr': {'greet': 'Bonjour'},
    })
    assert i18n.resolve('greet', 'fr') == 'Bonjour'
    assert i18n.resolve('greet', 'en') == 'Hello'
    assert i18n.resolve('only-en', 'fr') == 'Only'      # fr misses -> en fallback
    assert i18n.resolve('greet') == 'Hello'             # default locale = en


def test_missing_key_is_loud(tmp_path):
    _setup(tmp_path, {'en': {'x': 'X'}})
    assert i18n.resolve('nope', 'en') == '⧼nope⧽'


def test_param_substitution(tmp_path):
    _setup(tmp_path, {'en': {'hi': 'Hi $1, you have $2'}})
    assert i18n.resolve('hi', 'en', ('Sam', 3)) == 'Hi Sam, you have 3'


def test_param_multi_digit_not_mangled(tmp_path):
    _setup(tmp_path, {'en': {'k': '$1 and $2'}})
    # replacing $1 must not corrupt a would-be $10/$11 (we substitute high indices first)
    assert i18n.resolve('k', 'en', ('a', 'b')) == 'a and b'


def test_plural_english_rule(tmp_path):
    _setup(tmp_path, {'en': {'n': '$1 {{PLURAL:$1|statement|statements}}'}})
    assert i18n.resolve('n', 'en', (1,)) == '1 statement'
    assert i18n.resolve('n', 'en', (3,)) == '3 statements'
    assert i18n.resolve('n', 'en', (0,)) == '0 statements'


def test_qqx_returns_keys(tmp_path):
    _setup(tmp_path, {'en': {'greet': 'Hello'}})
    assert i18n.resolve('greet', 'qqx') == '(greet)'
    assert i18n.resolve('anything-at-all', 'qqx') == '(anything-at-all)'


def test_text_direction():
    assert i18n.text_direction('ar') == 'rtl'
    assert i18n.text_direction('he') == 'rtl'
    assert i18n.text_direction('ar-EG') == 'rtl'   # matched on base subtag
    assert i18n.text_direction('en') == 'ltr'
    assert i18n.text_direction('fr-CA') == 'ltr'
    assert i18n.text_direction('') == 'ltr'


def test_all_messages_fallback_and_qqx(tmp_path):
    _setup(tmp_path, {'en': {'@metadata': {}, 'a': 'A', 'b': 'B'}, 'fr': {'a': 'Aa'}})
    assert i18n.all_messages('fr') == {'a': 'Aa', 'b': 'B'}   # en-filled, @metadata excluded
    assert i18n.all_messages('qqx') == {'a': '(a)', 'b': '(b)'}


# ── End-to-end through the app ───────────────────────────────────────────────
# The templates are not wrapped in msg() yet (deferred), so there is no rendered
# English to assert on here — the request-scoped locale contract is what ships.

def test_uselang_cookie_persists_choice(client):
    resp = client.get('/?uselang=en')
    assert any('uselang=en' in c for c in resp.headers.getlist('Set-Cookie'))


def test_qqx_is_available_without_being_an_enabled_locale(app, client):
    # qqx is a QA locale, never offered to users — it must bypass ENABLED_LOCALES.
    assert 'qqx' not in app.config['ENABLED_LOCALES']
    with app.test_request_context('/api/v1/session?uselang=qqx'):
        app.preprocess_request()
        assert flask_g.locale == 'qqx'
        assert flask_g.dir == 'ltr'


def test_locale_falls_back_to_default_when_not_enabled(app):
    # A locale that exists in the catalogue but is not enabled must not be selected.
    with app.test_request_context('/api/v1/session?uselang=fr'):
        app.preprocess_request()
        assert flask_g.locale == app.config['DEFAULT_LOCALE']


def test_unenabled_locale_is_not_persisted_as_a_cookie(client):
    resp = client.get('/?uselang=fr')
    assert not any('uselang=' in c for c in resp.headers.getlist('Set-Cookie'))


# ── CI coverage guards on the real message catalogue ─────────────────────────
# These run against the committed i18n/en.json + qqq.json (not the tmp fixtures)
# so a new UI string that ships without documentation, or a malformed
# placeholder/PLURAL, fails CI rather than reaching translators on TWN.

import json as _json
import pathlib as _pathlib
import re as _re

_I18N_DIR = _pathlib.Path(__file__).resolve().parent.parent / 'i18n'


def _load(name):
    data = _json.loads((_I18N_DIR / name).read_text())
    return {k: v for k, v in data.items() if k != '@metadata'}


def test_every_en_message_is_documented():
    en = _load('en.json')
    qqq = _load('qqq.json')
    undocumented = sorted(set(en) - set(qqq))
    assert not undocumented, f'en.json keys missing a qqq.json doc: {undocumented}'


def test_no_orphan_qqq_docs():
    en = _load('en.json')
    qqq = _load('qqq.json')
    orphans = sorted(set(qqq) - set(en))
    assert not orphans, f'qqq.json documents keys not in en.json: {orphans}'


def test_placeholders_and_plurals_are_well_formed():
    en = _load('en.json')
    problems = []
    for key, msg in en.items():
        if msg.count('{{') != msg.count('}}'):
            problems.append(f'{key}: unbalanced {{{{ }}}}')
        # Every {{PLURAL:...}} must start with $N and contain at least one form.
        for pl in _re.findall(r'\{\{PLURAL:(.*?)\}\}', msg):
            if not pl.startswith('$') or '|' not in pl:
                problems.append(f'{key}: malformed PLURAL {{{{PLURAL:{pl}}}}}')
    assert not problems, 'malformed messages: ' + '; '.join(problems)


# ── The catalogue endpoint (GET /api/v1/i18n/<locale>) ───────────────────────
# This is what makes the catalogue consumable by the React SPA, and it is why the
# message map is NOT inlined into every HTML response.

def test_catalogue_endpoint_serves_the_full_english_map(client):
    resp = client.get('/api/v1/i18n/en')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == _load('en.json')
    assert '@metadata' not in body


def test_catalogue_endpoint_falls_back_to_english_for_an_unknown_locale(client):
    # Mirrors the resolver's locale -> en chain: a locale with no file is not a 404.
    resp = client.get('/api/v1/i18n/nl')
    assert resp.status_code == 200
    assert resp.get_json() == _load('en.json')


def test_catalogue_endpoint_serves_qqx_keys(client):
    body = client.get('/api/v1/i18n/qqx').get_json()
    assert body['base-skip-to-content'] == '(base-skip-to-content)'


def test_catalogue_endpoint_is_cacheable_only_when_the_build_is_pinned(client):
    # Same ?v=<git-sha> contract as the static assets (see _security_headers in app.py).
    assert client.get('/api/v1/i18n/en').headers['Cache-Control'] == 'no-store'
    pinned = client.get('/api/v1/i18n/en?v=deadbeef')
    assert pinned.headers['Cache-Control'] == 'public, max-age=604800'


# ── Key-existence guard: a typo'd key must fail CI, not ship as ⧼key⧽ ────────

_V2_ROOT = _I18N_DIR.parent

# msg('key') in Jinja, _('key') in Python. The literal must be followed directly by ','
# or ')', which excludes keys assembled at runtime — _('phase-label-' + stage['key']) —
# that a static scan cannot resolve. Those are guarded by their prefix, not here.
_CALL_SITE_RE = _re.compile(r"""\b(?:msg|_)\(\s*(['"])([A-Za-z0-9][A-Za-z0-9._-]*)\1\s*[,)]""")

_SCAN_GLOBS = ('*.py', 'api/*.py', 'services/*.py', 'templates/**/*.html')


def _scan_text(text):
    return [m.group(2) for m in _CALL_SITE_RE.finditer(text)]


def _message_call_sites():
    """{key: 'path:line'} for every statically resolvable message reference in v2/."""
    found = {}
    for pattern in _SCAN_GLOBS:
        for path in sorted(_V2_ROOT.glob(pattern)):
            if 'tests' in path.parts or '.venv' in path.parts or 'node_modules' in path.parts:
                continue
            for line_no, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                for key in _scan_text(line):
                    found.setdefault(key, f'{path.relative_to(_V2_ROOT)}:{line_no}')
    return found


def test_call_site_scanner_reads_literals_and_skips_runtime_built_keys():
    # Guards the guard: if this regex stops matching, the test below silently passes.
    assert _scan_text("{{ msg('base-log-out') }}") == ['base-log-out']
    assert _scan_text('{{ msg("base-log-out") }}') == ['base-log-out']
    assert _scan_text("msg('home-card-join-aria', c.title)") == ['home-card-join-aria']
    assert _scan_text("flash(_('flash-banned'), 'success')") == ['flash-banned']
    assert _scan_text("_('phase-label-' + stage['key'])") == []      # runtime-built: skipped
    assert _scan_text("thing_('not-a-message')") == []               # not a message call


def test_every_message_key_referenced_in_code_exists_in_en_json():
    en = _load('en.json')
    missing = sorted(
        f'{key} (at {where})'
        for key, where in _message_call_sites().items()
        if key not in en
    )
    assert not missing, (
        'message keys referenced in code but absent from i18n/en.json — these would '
        'render as ⧼key⧽ at runtime: ' + '; '.join(missing)
    )
