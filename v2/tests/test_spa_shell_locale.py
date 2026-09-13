"""The shell carries the negotiated locale, because the SPA cannot fetch it in time.

`index.html` is a build artifact served verbatim, which leaves two gaps the app cannot close
from inside itself. `<html lang="en">` is wrong for every other locale and `MessageProvider`
can only correct it after first paint. And the skip link and the loading fallback render
*above* that provider — it suspends on the session query, then waits on the catalogue fetch —
so they cannot call `msg()` at all. The skip link is the first thing a keyboard or
screen-reader user meets, so leaving it English in a translated interface is not cosmetic.

The server already negotiated the locale for this request, so it stamps both onto `<html>`.
"""

import re

import pytest

import i18n


def _html_tag(body):
    match = re.search(r'<html[^>]*>', body)
    assert match, f'no <html> tag in the served shell: {body[:120]!r}'
    return match.group(0)


@pytest.fixture
def shell(tmp_path, app):
    """A stand-in build, so these tests do not depend on a real SPA build being present."""
    build = tmp_path / 'spa'
    build.mkdir()
    (build / 'index.html').write_text(
        '<!doctype html>\n<html lang="en">\n<head><title>Proto</title></head>\n'
        '<body><div id="root"></div></body>\n</html>\n', encoding='utf-8')
    import app as app_module
    original, app_module._SPA_BUILD_DIR = app_module._SPA_BUILD_DIR, str(build)
    app_module._spa_shell_cache.clear()
    yield build
    app_module._SPA_BUILD_DIR = original
    app_module._spa_shell_cache.clear()


def test_the_shell_carries_the_negotiated_language_and_direction(client, shell):
    tag = _html_tag(client.get('/').get_data(as_text=True))
    assert 'lang="en"' in tag
    assert 'dir="ltr"' in tag


def test_the_shell_carries_the_messages_that_render_before_the_catalogue(client, shell):
    tag = _html_tag(client.get('/').get_data(as_text=True))
    # Both are read synchronously by app.tsx, above <MessageProvider>.
    assert f'data-msg-skip="{i18n.resolve("base-skip-to-content", "en")}"' in tag
    assert f'data-msg-loading="{i18n.resolve("base-loading-conversations", "en")}"' in tag


def test_a_requested_locale_reaches_the_shell(client, shell, app, tmp_path):
    """?uselang= changes the document language without the SPA having fetched anything."""
    directory = tmp_path / 'messages'
    directory.mkdir()
    (directory / 'en.json').write_text(
        '{"base-skip-to-content": "Skip to main content", '
        '"base-loading-conversations": "Loading conversations\\u2026"}', encoding='utf-8')
    (directory / 'nl.json').write_text('{"base-skip-to-content": "Ga naar de inhoud"}',
                                       encoding='utf-8')
    i18n.load(str(directory))
    app.config['ENABLED_LOCALES'] = ['en', 'nl']
    try:
        tag = _html_tag(client.get('/?uselang=nl').get_data(as_text=True))
        assert 'lang="nl"' in tag
        assert 'data-msg-skip="Ga naar de inhoud"' in tag
        # Untranslated in nl, so English fills it — the same per-key fallback the SPA gets.
        assert 'data-msg-loading="Loading conversations' in tag
    finally:
        i18n.load()


def test_the_shell_still_answers_when_the_build_is_missing(client, tmp_path):
    """This hook must never be the reason a broken deploy stops responding."""
    import app as app_module
    original, app_module._SPA_BUILD_DIR = app_module._SPA_BUILD_DIR, str(tmp_path / 'absent')
    app_module._spa_shell_cache.clear()
    try:
        assert client.get('/').status_code in (404, 500)   # handled, not an unhandled crash
    finally:
        app_module._SPA_BUILD_DIR = original
        app_module._spa_shell_cache.clear()


def test_a_stamped_message_cannot_break_out_of_the_attribute(client, shell, tmp_path):
    """Message text reaches an HTML attribute, so it has to be escaped."""
    directory = tmp_path / 'messages'
    directory.mkdir()
    (directory / 'en.json').write_text(
        '{"base-skip-to-content": "a \\" onload=\\"alert(1)", '
        '"base-loading-conversations": "x"}', encoding='utf-8')
    i18n.load(str(directory))
    try:
        tag = _html_tag(client.get('/').get_data(as_text=True))
        # The payload survives as inert text; what matters is that its quote was escaped, so
        # it cannot close data-msg-skip and start a new attribute.
        assert '&quot;' in tag
        assert 'onload=&quot;' in tag and 'onload="' not in tag
        # And the tag still has exactly the attributes we put on it.
        import re as _re
        assert sorted(_re.findall(r'(\b[a-z-]+)="', tag)) == [
            'data-msg-loading', 'data-msg-skip', 'dir', 'lang']
    finally:
        i18n.load()


def test_a_browser_header_does_not_choose_the_language(client, shell, app, tmp_path):
    """Both ends must reach the same locale, and only the server could see Accept-Language.

    A step only one end can perform shows up as a document that says one language while its
    content is another — the SPA fetches the catalogue for whatever *it* computed. It is also
    a surprise: a header set from an operating-system preference would hand someone a
    partly-translated interface they never asked for. The switcher makes it a choice.
    """
    directory = tmp_path / 'messages'
    directory.mkdir()
    (directory / 'en.json').write_text(
        '{"base-skip-to-content": "Skip to main content", "base-loading-conversations": "L"}',
        encoding='utf-8')
    (directory / 'nl.json').write_text('{"base-skip-to-content": "Ga naar de inhoud"}',
                                       encoding='utf-8')
    i18n.load(str(directory))
    app.config['ENABLED_LOCALES'] = ['en', 'nl']
    try:
        tag = _html_tag(client.get('/', headers={'Accept-Language': 'nl,en;q=0.5'})
                        .get_data(as_text=True))
        assert 'lang="en"' in tag
        assert 'data-msg-skip="Skip to main content"' in tag
        # Asking explicitly still works, and that is what the switcher's links do.
        tag = _html_tag(client.get('/?uselang=nl').get_data(as_text=True))
        assert 'lang="nl"' in tag
        assert 'data-msg-skip="Ga naar de inhoud"' in tag
    finally:
        i18n.load()


def test_a_missing_catalogue_stamps_english_not_a_key_marker(client, shell, tmp_path):
    """⧼base-skip-to-content⧽ in the skip link would be worse than English."""
    empty = tmp_path / 'empty'
    empty.mkdir()
    i18n.load(str(empty))
    try:
        tag = _html_tag(client.get('/').get_data(as_text=True))
        assert i18n._MISSING_L not in tag
        assert 'data-msg-skip="Skip to main content"' in tag
        assert 'data-msg-loading="Loading conversations' in tag
    finally:
        i18n.load()


def test_a_shell_whose_html_tag_differs_is_still_stamped(client, shell):
    """v2/static/spa is built at deploy time, so the tag's exact spelling is not ours."""
    (shell / 'index.html').write_text(
        "<!doctype html>\n<HTML lang=en data-build='x'>\n<body></body>\n</HTML>\n",
        encoding='utf-8')
    import app as app_module
    app_module._spa_shell_cache.clear()
    tag = _html_tag(client.get('/').get_data(as_text=True).replace('<HTML', '<html'))
    assert 'lang="en"' in tag and 'data-msg-skip=' in tag


def test_the_shell_revalidates_rather_than_forbidding_storage(client, shell):
    """no-store would make the page bfcache-ineligible, so Back would cold-boot the SPA."""
    response = client.get('/')
    assert response.headers['Cache-Control'] == 'private, no-cache'
    # Cookie only: the locale comes from ?uselang (part of the URL) or the uselang cookie.
    # Accept-Language is deliberately not consulted, so it must not appear here either.
    assert response.headers['Vary'] == 'Cookie'
    assert response.headers.get('ETag')
    # The ETag covers the stamped body, so it is locale-specific and conditional GET works.
    again = client.get('/', headers={'If-None-Match': response.headers['ETag']})
    assert again.status_code == 304


def test_a_shell_that_is_not_valid_utf8_does_not_take_the_hook_down(client, shell):
    """UnicodeDecodeError is a ValueError, not an OSError; it must not escape a before_request."""
    (shell / 'index.html').write_bytes(b'<!doctype html>\n<html lang="en">\xff\xfe</html>')
    import app as app_module
    app_module._spa_shell_cache.clear()
    assert client.get('/').status_code in (200, 404, 500)   # handled, not an unhandled crash


@pytest.mark.parametrize(('query', 'cookie', 'enabled', 'default', 'expected'), [
    ('?uselang=nl', None, ['en', 'nl'], 'en', 'nl'),      # explicit and offered
    ('?uselang=fr', None, ['en', 'nl'], 'en', 'fr'),      # explicit: honoured, not offered
    ('', 'nl', ['en', 'nl'], 'en', 'nl'),                 # remembered choice
    ('', 'nl', ['en'], 'en', 'en'),                       # remembered, since withdrawn
    ('', None, ['en', 'nl'], 'en', 'en'),                 # nothing asked
    ('', None, ['en', 'nl'], 'nl', 'nl'),                 # site default is not English
])
def test_the_shell_and_the_session_never_disagree(
    client, shell, app, query, cookie, enabled, default, expected,
):
    """The property the whole arrangement rests on, which nothing else asserted.

    Every other test here checks one end alone, which is how three divergent paths sat
    green: the server stamps <html lang> and the pre-catalogue strings, while the client
    picks the catalogue. If those disagree the page says one language and reads as another.
    """
    app.config['ENABLED_LOCALES'] = enabled
    app.config['DEFAULT_LOCALE'] = default
    if cookie:
        client.set_cookie('uselang', cookie)
    try:
        tag = _html_tag(client.get(f'/{query}').get_data(as_text=True))
        reported = client.get(f'/api/v1/session{query}').get_json()['data']['locales']['current']
        assert f'lang="{expected}"' in tag, tag
        assert reported == expected
    finally:
        client.delete_cookie('uselang')


def test_forcing_a_locale_by_url_previews_it_without_remembering_it(client, app, tmp_path):
    """?uselang= is the inspection door, and ENABLED_LOCALES governs the switcher.

    Forcing a locale that is not switched on renders the page in that language's direction
    with English filling the gaps — the familiar MediaWiki behaviour, and how a translator or
    an operator checks an RTL layout before enabling anything. It is deliberately not
    remembered: only an enabled locale is written to the cookie, so a preview does not follow
    the next reader on a shared machine or survive the query string.
    """
    directory = tmp_path / 'messages'
    directory.mkdir()
    (directory / 'en.json').write_text('{"greet": "Hello"}', encoding='utf-8')
    (directory / 'he.json').write_text('{"greet": "\u05e9\u05dc\u05d5\u05dd"}', encoding='utf-8')
    i18n.load(str(directory))
    app.config['ENABLED_LOCALES'] = ['en']
    try:
        forced = client.get('/?uselang=he')
        assert 'uselang' not in forced.headers.get('Set-Cookie', '')
        assert client.get('/api/v1/i18n/he').get_json()['greet'] == '\u05e9\u05dc\u05d5\u05dd'
        assert client.get('/api/v1/session?uselang=he').get_json()['data']['locales']['current'] == 'he'

        app.config['ENABLED_LOCALES'] = ['en', 'he']
        chosen = client.get('/?uselang=he')
        assert 'uselang=he' in chosen.headers.get('Set-Cookie', '')
    finally:
        client.delete_cookie('uselang')
        i18n.load()


def test_a_remembered_locale_is_dropped_once_it_stops_being_offered(client, app):
    """The cookie is the one path ENABLED_LOCALES still gates, on both ends."""
    app.config['ENABLED_LOCALES'] = ['en', 'nl']
    client.set_cookie('uselang', 'nl')
    try:
        assert 'lang="nl"' in _html_tag(client.get('/').get_data(as_text=True))
        app.config['ENABLED_LOCALES'] = ['en']
        assert 'lang="en"' in _html_tag(client.get('/').get_data(as_text=True))
    finally:
        client.delete_cookie('uselang')


def test_the_stamp_keeps_attributes_the_build_put_on_the_tag(client, shell):
    """Replacing the whole tag would drop them silently, with count==1 reporting success."""
    (shell / 'index.html').write_text(
        '<!doctype html>\n<html lang="en" class="no-js" data-build="abc">\n<body></body>\n</html>\n',
        encoding='utf-8')
    import app as app_module
    app_module._spa_shell_cache.clear()
    tag = _html_tag(client.get('/').get_data(as_text=True))
    assert 'class="no-js"' in tag
    assert 'data-build="abc"' in tag
    assert tag.count('lang=') == 1          # ours replaced theirs rather than joining it
