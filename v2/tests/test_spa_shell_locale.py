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
