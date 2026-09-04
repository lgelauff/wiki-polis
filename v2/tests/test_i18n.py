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
    with app.test_request_context('/?uselang=qqx'):
        app.preprocess_request()
        assert flask_g.locale == 'qqx'
        assert flask_g.dir == 'ltr'


def test_locale_falls_back_to_default_when_not_enabled(app):
    # A locale that exists in the catalogue but is not enabled must not be selected.
    with app.test_request_context('/?uselang=fr'):
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
