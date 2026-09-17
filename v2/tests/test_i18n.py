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


def test_plural_is_expanded_whatever_its_case(tmp_path):
    # Catches the server expanding only "{{PLURAL:" while the markup check, like banana,
    # accepts "{{plural:".
    _setup(tmp_path, {'en': {'n': '$1 {{PLURAL:$1|day|days}}'}, 'nl': {'n': '$1 {{plural:$1|dag|dagen}}'}})
    assert i18n.resolve('n', 'nl', (1,)) == '1 dag'
    assert i18n.resolve('n', 'nl', (3,)) == '3 dagen'


def test_qqx_returns_keys(tmp_path):
    _setup(tmp_path, {'en': {'greet': 'Hello'}})
    assert i18n.resolve('greet', 'qqx') == '(greet)'
    assert i18n.resolve('anything-at-all', 'qqx') == '(anything-at-all)'


def test_qqx_shows_the_parameters_it_was_given(tmp_path):
    # As MediaWiki's qqx: an interpolated value stays visible, so a coverage check can see
    # English passed into a message as well as English written around one.
    _setup(tmp_path, {'en': {'hi': 'Hello $1, from $2'}})
    assert i18n.resolve('hi', 'qqx', ('Ada', 'Proto')) == '(hi: Ada, Proto)'


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
    (tmp_path / 'params').mkdir()
    _setup(tmp_path / 'params', {'en': {'one': 'Hi $1', 'three': '$3 of $1', 'plural': '{{PLURAL:$2|a|b}}'}})
    assert i18n.all_messages('qqx') == {'one': '(one: $1)', 'three': '(three: $1, $2, $3)', 'plural': '(plural: $1, $2)'}


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


def test_an_unenabled_locale_can_be_forced_but_is_not_remembered(app):
    """ENABLED_LOCALES governs the switcher, not what ?uselang= may reach.

    Forcing a locale renders the page in that language's direction with English filling
    whatever is untranslated — the familiar MediaWiki behaviour, and how a translator or an
    operator previews a language, or an RTL layout, before switching it on. This test used to
    assert the opposite; the change is deliberate, and the guarantee that replaced it is the
    one below: a preview is never persisted, so it cannot follow the next reader.
    """
    with app.test_request_context('/api/v1/session?uselang=fr'):
        app.preprocess_request()
        assert flask_g.locale == 'fr'
        assert flask_g.get('_persist_locale') is None


def test_unenabled_locale_is_not_persisted_as_a_cookie(client):
    resp = client.get('/?uselang=fr')
    assert not any('uselang=' in c for c in resp.headers.getlist('Set-Cookie'))


def test_a_remembered_locale_is_dropped_once_it_stops_being_offered(app):
    """The cookie is the one path ENABLED_LOCALES still gates — otherwise withdrawing a
    locale would strand returning readers on it."""
    app.config['ENABLED_LOCALES'] = ['en']
    with app.test_request_context('/api/v1/session', headers={'Cookie': 'uselang=fr'}):
        app.preprocess_request()
        assert flask_g.locale == app.config['DEFAULT_LOCALE']


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


def _absent_locale():
    """A locale code with no file in i18n/, computed rather than hardcoded.

    This test used to ask for 'nl'. That was fine until translatewiki delivered Dutch, at
    which point the first translation the project ever received would have turned this test
    red -- a delivered translation must never break the build.
    """
    present = {p.stem for p in _I18N_DIR.glob('*.json')}
    for candidate in ('zxx', 'xx', 'qtz', 'und'):
        if candidate not in present:
            return candidate
    raise AssertionError(f'no absent locale left to test with; present: {sorted(present)}')


def test_catalogue_endpoint_falls_back_to_english_for_an_unknown_locale(client):
    # Mirrors the resolver's locale -> en chain: a locale with no file is not a 404.
    resp = client.get(f'/api/v1/i18n/{_absent_locale()}')
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

# _('key') in Python, msg('key') in the SPA. The literal must be followed directly by ','
# or ')', which excludes keys assembled at runtime — _('phase-label-' + stage['key']) —
# that a static scan cannot resolve. Those are guarded by their prefix, not here.
_CALL_SITE_RE = _re.compile(r"""\b(?:msg|_)\(\s*(['"])([A-Za-z0-9][A-Za-z0-9._-]*)\1\s*[,)]""")

# The React SPA is the only surface, so frontend/src is the half that matters. The Python
# globs stay because server-side copy may yet be keyed. There is no templates/ glob: the
# Jinja frontend was deleted, and a glob that matches nothing reads like coverage.
_SCAN_GLOBS = (
    '*.py', 'api/*.py', 'services/*.py',
    'frontend/src/**/*.ts', 'frontend/src/**/*.tsx',
)


# Keys reached indirectly: server-labels.ts maps a server identifier to a message key, so
# the only msg() call there passes a variable and _CALL_SITE_RE cannot see the keys. Scan the
# map values instead, keyed on the `<id>: 'message-key',` shape those tables use. Without
# this the explicit tables are exactly as invisible to the guard as the concatenated key they
# were written to replace -- which is how the previous generation of these keys rotted.
_MAP_KEY_RE = _re.compile(r"""^\s*'?[A-Za-z0-9_-]+'?\s*:\s*'([a-z0-9][a-z0-9._-]*)'\s*,""", _re.M)

_INDIRECT_KEY_FILES = ('frontend/src/i18n/server-labels.ts',)


def _scan_text(text):
    return [m.group(2) for m in _CALL_SITE_RE.finditer(text)]


def _scan_map_values(text):
    return _MAP_KEY_RE.findall(text)


# Keys no call site spells out, because the code builds them. Each is listed with the file
# that builds it and is checked below to still exist, so this cannot become a list of keys
# that quietly outlive their caller.
_RUNTIME_KEYS = {
    # error_pages.py: f'errorpage-{code}-{part}' over its _ERRORS table, plus the code label.
    'error_pages.py': [
        f'errorpage-{code}-{part}'
        for code in (403, 404, 500)
        for part in ('title', 'message', 'hint')
    ] + ['errorpage-code'],
    # app.py: _SPA_BOOTSTRAP_MESSAGES, stamped onto <html> as data-msg-* before the SPA has
    # a catalogue to read.
    'app.py': ['base-skip-to-content', 'base-loading-conversations'],
}


def test_runtime_built_keys_still_exist():
    """Guards the list above: a key retired without its caller must fail here, not linger."""
    en = _load('en.json')
    missing = sorted(f'{key} (built in {where})'
                     for where, keys in _RUNTIME_KEYS.items()
                     for key in keys if key not in en)
    assert not missing, 'keys built at runtime but absent from en.json: ' + '; '.join(missing)


def _message_call_sites():
    """{key: 'path:line'} for every statically resolvable message reference in v2/."""
    found = {}
    for pattern in _SCAN_GLOBS:
        for path in sorted(_V2_ROOT.glob(pattern)):
            if 'tests' in path.parts or '.venv' in path.parts or 'node_modules' in path.parts:
                continue
            indirect = str(path.relative_to(_V2_ROOT)) in _INDIRECT_KEY_FILES
            for line_no, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                keys = _scan_text(line)
                if indirect:
                    keys = keys + _scan_map_values(line)
                for key in keys:
                    found.setdefault(key, f'{path.relative_to(_V2_ROOT)}:{line_no}')
    for where, keys in _RUNTIME_KEYS.items():
        for key in keys:
            found.setdefault(key, f'{where} (built at runtime)')
    return found


def test_call_site_scanner_reads_literals_and_skips_runtime_built_keys():
    # Guards the guard: if this regex stops matching, the test below silently passes.
    assert _scan_text("{{ msg('base-log-out') }}") == ['base-log-out']
    assert _scan_text('{{ msg("base-log-out") }}') == ['base-log-out']
    assert _scan_text("msg('home-card-join-aria', c.title)") == ['home-card-join-aria']
    assert _scan_text("flash(_('flash-banned'), 'success')") == ['flash-banned']
    assert _scan_text("_('phase-label-' + stage['key'])") == []      # runtime-built: skipped
    assert _scan_text("thing_('not-a-message')") == []               # not a message call

    # The indirect scan, guarded the same way: server-labels.ts reaches its keys through a
    # map, and if this regex stops matching that shape the key check below silently stops
    # covering those keys.
    assert _scan_map_values("  vote: 'conv-tab-vote',") == ['conv-tab-vote']
    assert _scan_map_values("  'informed-voting': 'conv-tab-informed',") == ['conv-tab-informed']
    assert _scan_map_values("  cleanup_window: 'phase-label-cleanup',") == ['phase-label-cleanup']
    assert _scan_map_values("import type {Message} from './messages';") == []
    assert _scan_map_values("  const key = id ? table[id] : undefined;") == []


def test_indirect_key_files_are_actually_scanned():
    """The file named in _INDIRECT_KEY_FILES must exist and yield keys.

    A typo'd path would make the scan vacuous without failing anything -- the same class of
    silent hole as the deleted templates/ glob this scanner used to carry.
    """
    for relative in _INDIRECT_KEY_FILES:
        path = _V2_ROOT / relative
        assert path.exists(), f'_INDIRECT_KEY_FILES names a missing file: {relative}'
        assert _scan_map_values(path.read_text(encoding='utf-8')), (
            f'no message keys found in {relative} -- has its map shape changed?'
        )


def test_every_message_key_referenced_in_code_exists_in_en_json():
    # The converted screens give this real call sites to check. The scanner has its own
    # test above regardless: it keeps the regex honest, so this cannot quietly go back to
    # asserting over an empty set if the globs or the call syntax drift.
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


# ── The SPA duplicates two server-side tables; pin them together ─────────────

def _ts_source(relative):
    return (_I18N_DIR.parent / 'frontend' / 'src' / relative).read_text(encoding='utf-8')


def test_spa_rtl_language_list_matches_the_resolver():
    """A divergent list means `dir` disagrees with the server for some language.

    The SPA owns the <html> attributes (one shell serves every locale, and ?uselang= can
    change the locale without a new document), so it carries its own copy of _RTL_LANGS.
    Hand-copying it dropped seven languages on the first attempt; this keeps the two honest.
    """
    listed = set(_re.findall(
        r"'([a-z-]+)'",
        _re.search(r'RTL_LANGS = new Set\(\[(.*?)\]\)',
                   _ts_source('i18n/messages.tsx'), _re.S).group(1),
    ))
    assert listed == i18n._RTL_LANGS, (
        'frontend/src/i18n/messages.tsx RTL_LANGS has drifted from i18n._RTL_LANGS: '
        f'only in SPA={sorted(listed - i18n._RTL_LANGS)}, '
        f'only in resolver={sorted(i18n._RTL_LANGS - listed)}'
    )


# ── Delivered translations: what the sync bot commits must not be able to break us ──

def test_a_malformed_delivered_file_falls_back_to_english_entirely(tmp_path):
    """translatewiki commits `i18n/<code>.json` with no human in the loop.

    `load()` skips a file it cannot parse, so the locale simply never exists and every lookup
    falls through to English. Worth pinning: this is the property that makes an automated
    delivery safe to merge, and it is cheaper than validating the bot's output in CI.
    """
    directory = _setup(tmp_path, {'en': {'greet': 'Hello', 'bye': 'Bye'}})
    (directory / 'nl.json').write_text('{ this is not json', encoding='utf-8')
    i18n.load(str(directory))

    assert not i18n.has_locale('nl')
    assert i18n.resolve('greet', 'nl') == 'Hello'
    assert i18n.all_messages('nl') == {'greet': 'Hello', 'bye': 'Bye'}


def test_a_non_string_value_in_a_delivered_file_is_ignored(tmp_path):
    """Only strings are messages; anything else falls back rather than reaching a template."""
    _setup(tmp_path, {
        'en': {'greet': 'Hello', 'count': 'One'},
        'nl': {'greet': 'Hallo', 'count': {'unexpected': 'object'}},
    })
    assert i18n.resolve('greet', 'nl') == 'Hallo'
    assert i18n.resolve('count', 'nl') == 'One'          # not the dict, not a crash


def test_a_translation_for_a_deleted_message_is_not_served(tmp_path):
    """A stale translated key must be inert, not additive.

    translatewiki keeps a translation until it next syncs, so after a key is deleted from
    en.json the delivered file still carries it. English defines what exists and a translation
    only supplies values, so the stale entry must not reach the client -- otherwise deleting a
    key would mean waiting for translatewiki to catch up, or hand-editing a delivered file,
    which `plan_i18n.md` rule 1 forbids.
    """
    _setup(tmp_path, {
        'en': {'greet': 'Hello'},
        'nl': {'greet': 'Hallo', 'since-deleted': 'Verwijderd'},
    })
    served = i18n.all_messages('nl')

    assert served == {'greet': 'Hallo'}
    assert 'since-deleted' not in served
    # The resolver may still answer for it; only the served catalogue is authoritative about
    # which messages exist, and that is what the SPA loads.
    assert set(served) == {'greet'}


# ── The language switcher's data ─────────────────────────────────────────────

def test_the_session_offers_the_enabled_locales_with_their_own_names(client, app):
    """The switcher shows autonyms: someone looking for Dutch scans for "Nederlands"."""
    app.config['ENABLED_LOCALES'] = ['en', 'nl']
    data = client.get('/api/v1/session').get_json()['data']
    assert data['locales']['current'] == 'en'
    assert data['locales']['available'] == [
        {'code': 'en', 'name': 'English'},
        {'code': 'nl', 'name': 'Nederlands'},
    ]


def test_the_session_reports_the_locale_this_request_negotiated(client, app):
    app.config['ENABLED_LOCALES'] = ['en', 'nl']
    data = client.get('/api/v1/session?uselang=nl').get_json()['data']
    assert data['locales']['current'] == 'nl'


def test_an_unnamed_locale_degrades_to_its_code_rather_than_blank():
    """Autonyms are added alongside each translation, so a new code may arrive first."""
    assert i18n.language_name('en') == 'English'
    assert i18n.language_name('zxx') == 'zxx'


def test_a_malformed_uselang_is_ignored_on_both_ends(app):
    """banana-i18n throws on a code that is not a well-formed tag.

    It is constructed in the render body of the provider wrapping every route, with no error
    boundary above it, so an unfiltered ?uselang blanks the page — and `en_US` is exactly what
    someone reaching for the inspection door types. The gate here must stay identical to
    USELANG_RE in frontend/src/i18n/messages.tsx, or the two ends reject different inputs.
    """
    for bad in ('en_US', 'en US', '  ', '<script>', 'e', 'toolongcode', 'nl%E4'):
        with app.test_request_context(f'/api/v1/session?uselang={bad}'):
            app.preprocess_request()
            assert flask_g.locale == app.config['DEFAULT_LOCALE'], bad
    for good in ('en', 'he', 'qqx', 'pt-br', 'he-IL'):
        with app.test_request_context(f'/api/v1/session?uselang={good}'):
            app.preprocess_request()
            assert flask_g.locale == good, good


def test_the_uselang_gate_matches_the_one_the_spa_uses():
    """Same inputs rejected on both ends, or a crafted link reaches banana on one of them."""
    import re as _re
    from pathlib import Path
    import app as app_module

    source = (Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'i18n' / 'messages.tsx'
              ).read_text(encoding='utf-8')
    spa = _re.search(r'const USELANG_RE = /\^(.+)\$/;', source)
    assert spa, 'USELANG_RE not found in messages.tsx — has it been renamed?'
    assert spa.group(1) == app_module._USELANG_RE.pattern.strip('^$'), (
        'the SPA and the server gate ?uselang differently; they must reject the same inputs'
    )


def test_a_percent_encoded_cookie_is_read_the_same_way_the_spa_reads_it(app):
    """The client decodes the cookie, so the server must too.

    Otherwise `uselang=%6El` is rejected here and accepted as `nl` there — a disagreement on
    the one path both ends are supposed to gate identically.
    """
    app.config['ENABLED_LOCALES'] = ['en', 'nl']
    with app.test_request_context('/api/v1/session', headers={'Cookie': 'uselang=%6El'}):
        app.preprocess_request()
        assert flask_g.locale == 'nl'


def test_a_qqx_cookie_is_refused(app):
    """?uselang=qqx works; a qqx cookie is something the server never writes.

    Honouring one on the client would guarantee a disagreement: the page saying one language
    while every wired string renders as (message-key).
    """
    app.config['ENABLED_LOCALES'] = ['en', 'nl']
    with app.test_request_context('/api/v1/session', headers={'Cookie': 'uselang=qqx'}):
        app.preprocess_request()
        assert flask_g.locale == app.config['DEFAULT_LOCALE']


# ── Markup in translations: what may reach innerHTML ─────────────────────────────────────
#
# The hostile cases were checked against banana-i18n 2.4.0, the SPA's renderer: each either
# reaches the page as live HTML or makes banana throw. i18n.py explains, above
# markup_signature(), why the check runs at load.

_EN_BOLD = '<strong>$1</strong> {{PLURAL:$1|day|days}} left'
_EN_LINK = 'Go to <a href="/">the front page</a> to start again.'


@pytest.mark.parametrize('translation', [
    'Nog <img src="x" onerror="alert(1)"/> dagen',                     # self-closing keeps attributes
    'Nog {{PLURAL:$1|<img src=x onerror=alert(1)>|dagen}}',            # PLURAL branch passes raw HTML
    '{{GENDER:$1|<img src=x onerror=alert(1)>|b}}',                    # so does GENDER
    '<strong onmouseover="alert(1)"/>$1',                              # attribute on an allowed tag
    '<strong onclick="alert(1)">$1</strong>',
    '<!-- x --><strong>$1</strong>',
])
def test_markup_the_english_does_not_use_is_refused(translation):
    assert not i18n.markup_is_permitted(translation, _EN_BOLD)


@pytest.mark.parametrize('translation', [
    'nog < 1 dag',                                                     # a "<" that starts no tag
    '< strong>$1</strong> dagen',                                      # whitespace inside a tag
    '<strong>$1</ strong> dagen',
    '<strong>$1< /strong> dagen',
    '$1</strong> dagen',                                               # closing tag with no opener
    '<strong>$1</strong></strong> dagen',
    '<strong>$1 dagen',                                                # opener never closed
    '<strong />$1 dagen',                                              # self-closing allowed tag
    '<strong>$1</strong> {{PLURAL:$1|dag|dagen',                       # unclosed {{
    '<strong>$1</strong> {{PLURL:$1|dag|dagen}}',                      # unknown function
    '<strong>$1</strong> {{dagen}}',
    # banana-i18n 2.4.0 throws on each of these, or prints "undefined".
    'US$ 5 voor <strong>$1</strong>',                                  # "$" not a placeholder
    '<strong>$1</strong> 5 $',
    '<strong>$1</strong> dagen\\',                                    # backslash
    '<strong>$1</strong> {dagen}',                                     # lone braces
    '<strong>$1</strong> }}} dagen',
    '{{{PLURAL:$1|dag|dagen}}} <strong>$1</strong>',
    '}} {{PLURAL:$1|dag|dagen}} <strong>$1</strong>',
    '<strong>$1</strong> {{PLURAL: $1|dag|dagen}}',                    # space before the argument
    '<strong>$1</strong> {{PLURAL:$1a|dag|dagen}}',                    # argument not a placeholder
    '<strong>$1</strong> {{PLURAL:$1|}}',                              # empty branch -> "undefined"
    '<strong>$1</strong> {{PLURAL:$1|2=twee}}',                        # explicit forms only
    '<b>{{PLURAL:$1|x</b>|y}}',                                        # tag closed in another branch
    '{{PLURAL:$1|<strong>$1|dagen</strong>}}',                         # tag spanning two branches
    '<strong>$1</strong> {{PLURAL:$|dag|dagen}}',                      # "$" with no number
    'a $² <strong>$1</strong>',                                        # a digit banana does not read
    '<strong>$1</strong> {{PLURAL:$①|dag|dagen}}',
    '<b>' * 30 + '$1' + '</b>' * 30,                                   # nested beyond any message
])
def test_text_banana_cannot_parse_is_refused(translation):
    # Catches a translation that passes the tag comparison but makes banana throw, which
    # would show the message key to readers instead of the English fallback.
    assert not i18n.markup_is_permitted(translation, _EN_BOLD)


def test_tags_that_do_not_nest_are_refused():
    # banana escapes the whole message when tags cross, even when English uses both tags.
    english = '<strong>Bold</strong> and <em>emphasis</em>'
    assert not i18n.markup_is_permitted('<strong>Vet <em>nadruk</strong></em>', english)
    assert i18n.markup_is_permitted('<em>Nadruk</em> en <strong>vet</strong>', english)


@pytest.mark.parametrize('translation', [
    'Ga naar <a href="javascript:alert(1)">de voorpagina</a>.',
    'Ga naar <a href="https://evil.example/">de voorpagina</a>.',
    'Ga naar <a href="/" onclick="alert(1)">de voorpagina</a>.',
    'Ga naar <a href="/" target="_blank">de voorpagina</a>.',
    'Ga naar <a href="\'/\'">de voorpagina</a>.',                       # quotes inside the value
    'Ga naar <a href="/\'">de voorpagina</a>.',
    'Ga naar <a href=/>de voorpagina</a>.',                             # unquoted value
    'Ga naar <a/href="/">de voorpagina</a>.',
    'Ga naar <a href="/" "<>">de voorpagina</a>.',                      # junk after the attribute
    'Ga naar <a href="/" href="/x">de voorpagina</a>.',                 # a second href
])
def test_a_link_may_not_change_where_it_goes_or_what_it_does(translation):
    assert not i18n.markup_is_permitted(translation, _EN_LINK)


@pytest.mark.parametrize('translation, english', [
    # Each would read as the same tag and attributes as its English if the scanner took any
    # delimiter as a quote, or let attributes run together. banana-i18n throws on both, which
    # would replace the whole message with its key on the page.
    ('Ga naar <a href=|/|>de voorpagina</a>.', _EN_LINK),
    ('Ga naar <a href="/"title="x">de voorpagina</a>.', 'Go to <a href="/" title="x">the front page</a>.'),
])
def test_a_tag_is_only_read_the_way_banana_reads_it(translation, english):
    assert not i18n.markup_is_permitted(translation, english)


def test_braces_in_an_attribute_value_are_refused_even_when_english_has_them():
    # banana escapes the whole message when a value holds "{", so its tags show as text.
    text = 'Ga naar <a href="/{x}">de voorpagina</a>.'
    assert not i18n.markup_is_permitted(text, text)


def test_a_very_long_placeholder_is_refused_rather_than_raising():
    # Catches the refusal reason converting placeholder numbers with int(): Python refuses
    # more than 4300 digits, and load() runs this at import, so one string would stop the app.
    problem = i18n.markup_problem('Hallo $' + '1' * 5000, 'Hello $1')
    assert problem is not None and 'placeholders' in problem


@pytest.mark.parametrize('translation, english', [
    ('<strong>$1</strong> {{PLURAL:$1|dag|dagen}} over', _EN_BOLD),
    # A language may repeat the English markup in each plural branch, or reorder it.
    ('{{PLURAL:$1|nog <strong>$1</strong> dag|nog <strong>$1</strong> dagen}}', _EN_BOLD),
    ('{{plural:$1|<strong>$1</strong> dag|<strong>$1</strong> dagen}}', _EN_BOLD),
    ('Ga <a href="/">naar de voorpagina</a> om opnieuw te beginnen.', _EN_LINK),
    ("Ga naar <a  href = '/' >de voorpagina</a>.", _EN_LINK),                 # whitespace, quote style
    ('Geen opmaak', _EN_BOLD),                                               # dropping it is fine
    ('Terug over &lt;1 minuut', 'Back in under 1m'),                         # an entity is not a tag
    ('{{GRAMMAR:genitive|<strong>$1</strong>}} dagen', _EN_BOLD),            # GRAMMAR takes a word
])
def test_markup_the_english_already_uses_is_allowed(translation, english):
    assert i18n.markup_is_permitted(translation, english)


@pytest.mark.parametrize('hostile', [
    '<' + ' ' * 50_000,
    '<a' + 'b' * 50_000,                                               # quadratic for the old regex
    '</a' + 'b' * 50_000,
    'Klik <b' + 'dag' * 17_000,
    '<a' + ' x="' * 20_000,
    '{{PLURAL:$1|' * 20_000,
    '<b>' * 20_000,
])
def test_the_check_takes_linear_time_on_hostile_input(hostile):
    # Catches a scanner that backtracks or recurses without bound: load() runs this over every
    # message of every translation at import, in every worker.
    import time
    started = time.perf_counter()
    assert not i18n.markup_is_permitted(hostile, '<a href="/">x</a>')
    assert time.perf_counter() - started < 0.5


def test_a_refusal_says_why():
    assert 'adds markup' in i18n.markup_problem('<em>x</em>', '<strong>x</strong>')
    assert '<em>' in i18n.markup_problem('<em>x</em>', '<strong>x</strong>')
    assert 'cannot be parsed' in i18n.markup_problem('a < b', 'a')
    assert 'at character 3' in i18n.markup_problem('a < b', 'a')
    assert 'placeholders its English does not have: $2' in i18n.markup_problem('$1 en $2', '$1')
    assert i18n.markup_problem('<strong>x</strong>', '<strong>y</strong>') is None


def test_a_translation_with_foreign_markup_is_not_served(tmp_path):
    """English is served for that one message, on every path that renders HTML."""
    _setup(tmp_path, {
        'en': {'hint': _EN_LINK, 'left': _EN_BOLD, 'plain': 'Hello'},
        'nl': {
            'hint': 'Ga naar <a href="javascript:alert(1)">de voorpagina</a>.',
            'left': '<strong>$1</strong> {{PLURAL:$1|dag|dagen}} over',
            'plain': 'Hallo <img src=x onerror=alert(1)>',
        },
    })
    # resolve() is what error_pages.py renders the unescaped hint through.
    assert i18n.resolve('hint', 'nl') == _EN_LINK
    assert i18n.resolve('left', 'nl', (2,)) == '<strong>2</strong> dagen over'
    # all_messages() is the catalogue endpoint the SPA feeds to banana and innerHTML.
    served = i18n.all_messages('nl')
    assert served['hint'] == _EN_LINK
    assert served['plain'] == 'Hello'
    assert served['left'] == '<strong>$1</strong> {{PLURAL:$1|dag|dagen}} over'
    assert sorted(i18n.refused_translations()['nl']) == ['hint', 'plain']
    assert 'javascript' in i18n.refused_translations()['nl']['hint']


def test_no_translation_is_served_without_english_to_compare_it_with(tmp_path):
    # Catches the check failing open: with en.json unreadable, or for a key English does not
    # have, a translation would otherwise be served exactly as it arrived.
    d = tmp_path / 'i18n'
    d.mkdir()
    (d / 'en.json').write_text('{ not json', encoding='utf-8')
    (d / 'nl.json').write_text(json.dumps({'hint': 'Klik <img src=x onerror=alert(1)>'}), encoding='utf-8')
    i18n.load(str(d))
    assert i18n.resolve('hint', 'nl') == '⧼hint⧽'
    assert i18n.refused_translations() == {'nl': {'hint': 'en.json did not load'}}

    (tmp_path / 'second').mkdir()
    _setup(tmp_path / 'second', {'en': {'kept': 'Kept'}, 'nl': {'kept': 'Bewaard', 'stale': '<img src=x onerror=alert(1)>'}})
    assert i18n.resolve('stale', 'nl') == '⧼stale⧽'
    assert i18n.resolve('kept', 'nl') == 'Bewaard'
    # A key English no longer has is set aside as stale, not reported as a markup failure.
    assert i18n.stale_translations() == {'nl': ['stale']}
    assert i18n.refused_translations() == {}


def test_refusals_are_logged_with_their_reasons(tmp_path, caplog):
    import logging
    _setup(tmp_path, {'en': {'hint': _EN_LINK}, 'nl': {'hint': 'Klik <img src=x>', 'gone': 'Weg'}})
    with caplog.at_level(logging.INFO):
        i18n.log_refusals(logging.getLogger('test'))
    assert 'nl.json: not serving 1 message(s): hint: it cannot be parsed' in caplog.text
    assert 'awaiting the next translatewiki export: gone' in caplog.text


def test_the_app_logs_refusals_once_logging_is_configured():
    # Catches the create_app wiring being dropped or moved before logging exists: load() runs
    # at import, so without this call nothing reports a refused translation. create_app()
    # cannot be called a second time in one process, so the order is checked in its source.
    import inspect

    import app as app_module
    source = inspect.getsource(app_module.create_app)
    assert 'i18n.log_refusals(app.logger)' in source
    assert source.index('configure_logging(app') < source.index('i18n.log_refusals(app.logger)')


def test_the_catalogue_endpoint_never_serves_a_refused_translation(tmp_path, client):
    _setup(tmp_path, {
        'en': {'errorpage-404-hint': _EN_LINK},
        'nl': {'errorpage-404-hint': 'Klik <img src=x onerror=alert(1)>'},
    })
    body = client.get('/api/v1/i18n/nl').get_json()
    assert body['errorpage-404-hint'] == _EN_LINK


def _markup_violations(directory):
    """'file: key: reason' for every translation in ``directory`` that would not be served.

    Reads the files from disk, not through i18n._MESSAGES, which has already dropped the
    offending values."""
    en = json.loads((directory / 'en.json').read_text(encoding='utf-8'))
    found = []
    for path in sorted(directory.glob('*.json')):
        if path.stem in (i18n.SOURCE_LOCALE, 'qqq'):
            continue
        for key, text in json.loads(path.read_text(encoding='utf-8')).items():
            if key == '@metadata' or not isinstance(text, str):
                continue
            if key not in en:
                # Stale, not wrong: removing a message from en.json must not turn CI red until
                # translatewiki's next export drops it. load() sets it aside either way.
                continue
            if (problem := i18n.markup_problem(text, en[key])) is not None:
                found.append(f'{path.name}: {key}: {problem}')
    return found


def test_the_translation_gate_reports_a_bad_delivered_file(tmp_path):
    # Catches the gate below passing vacuously: at present there is no delivered translation
    # for it to read, so it is exercised here against one.
    (tmp_path / 'en.json').write_text(json.dumps({'hint': _EN_LINK, 'plain': 'Hello'}), encoding='utf-8')
    (tmp_path / 'qqq.json').write_text(json.dumps({'hint': '<img src=x>'}), encoding='utf-8')
    (tmp_path / 'nl.json').write_text(json.dumps({
        '@metadata': {'authors': []},
        'hint': 'Ga naar <a href="/" onclick="x">de voorpagina</a>.',
        'plain': 'Hallo',
        'gone': 'Weg',
    }), encoding='utf-8')
    violations = _markup_violations(tmp_path)
    assert len(violations) == 1
    assert violations[0].startswith('nl.json: hint: it adds markup') and 'onclick' in violations[0]
    # A key removed from English is not a violation: the gate must not block that change.
    assert not any('gone' in line for line in violations)


def test_every_delivered_translation_passes_the_markup_check():
    """The CI gate: a translation that would not be served fails the change that brings it."""
    violations = _markup_violations(_I18N_DIR)
    assert not violations, 'translations that would not be served:\n' + '\n'.join(violations)


# The source is ours, but it is the ceiling every translation is held to, so it is held to an
# allowlist too. Adding a tag here widens what every translation may use. Note that the SPA's
# banana-i18n escapes <a> written in message text, so a link in a message renders only on
# the server-rendered error pages; SPA links are passed in as parameters.
_SOURCE_TAGS = {'strong', 'em', 'code', 'a'}
_SOURCE_ATTRIBUTES = {('a', 'href')}
_SAME_SITE_PATH = _re.compile(r'/(?![/\\])[^\s"\'<>\\]*')


def test_source_messages_use_only_allowlisted_markup():
    en = json.loads((_I18N_DIR / 'en.json').read_text(encoding='utf-8'))
    problems = []
    for key, text in en.items():
        if key.startswith('@') or not isinstance(text, str):
            continue
        signature = i18n.markup_signature(text)
        if signature is None:
            problems.append(f'{key}: cannot be parsed by banana-i18n')
            continue
        for _closing, tag, attrs in signature:
            if tag not in _SOURCE_TAGS:
                problems.append(f'{key}: <{tag}>')
            for name, value in attrs:
                if (tag, name) not in _SOURCE_ATTRIBUTES:
                    problems.append(f'{key}: <{tag} {name}>')
                elif not _SAME_SITE_PATH.fullmatch(value):
                    problems.append(f'{key}: <{tag} {name}="{value}"> is not a same-site path')
    assert not problems, '; '.join(problems)


@pytest.mark.parametrize('value, same_site', [
    ('/', True), ('/c/some-slug', True), ('//evil.example', False), ('/\\evil.example', False),
    ('https://example.org/', False), ('javascript:alert(1)', False),
])
def test_the_same_site_path_rule(value, same_site):
    assert bool(_SAME_SITE_PATH.fullmatch(value)) is same_site
