"""Unit tests for the i18n message loader/resolver (v2/i18n.py)."""

import json

import pytest

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


# ── End-to-end through the app (base.html is converted) ──────────────────────

def test_page_renders_english_by_default(client):
    body = client.get('/').get_data(as_text=True)
    assert 'Skip to main content' in body          # base-skip-to-content in English
    assert 'window.wpMessages' in body             # client message island present
    assert '<html lang="en"' in body

def test_qqx_renders_message_keys(client):
    body = client.get('/?uselang=qqx').get_data(as_text=True)
    assert '(base-skip-to-content)' in body        # keys shown -> string is externalised
    assert 'Skip to main content' not in body      # the English is gone under qqx

def test_uselang_cookie_persists_choice(client):
    resp = client.get('/?uselang=en')
    assert any('uselang=en' in c for c in resp.headers.getlist('Set-Cookie'))
