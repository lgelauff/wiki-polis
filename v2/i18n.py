"""i18n.py — minimal message store + resolver for the wiki-polis UI.

Uses the translatewiki.net (TWN) "banana" JSON format: source strings live in
``i18n/en.json`` (English = source locale), documentation in ``i18n/qqq.json``, and
translations arrive as ``i18n/<code>.json`` from TWN. The same JSON drives the client
side via banana-i18n, so there is ONE message format for server and browser.

No third-party dependency — a small loader + resolver over the stdlib. Resolution
supports ``$1..$n`` parameter substitution, ``{{PLURAL:$n|a|b}}`` expansion, and
English fallback. A ``qqx`` debug locale renders message *keys* instead of text, which
is the standard way to verify every UI string has been externalised (any real English
still on screen under ``?uselang=qqx`` is a missed string).
"""

import json
import os
import re

_I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n')

SOURCE_LOCALE = 'en'
DEBUG_LOCALE = 'qqx'   # renders message keys, for i18n coverage QA

# Right-to-left languages (base ISO-639 subtags). Extend as RTL locales are enabled.
_RTL_LANGS = {
    'ar', 'arc', 'ary', 'arz', 'azb', 'ckb', 'dv', 'fa', 'ha', 'he', 'khw', 'ks',
    'ku', 'mzn', 'nqo', 'pnb', 'ps', 'sd', 'ug', 'ur', 'yi',
}

# Autonyms — a language's name in that language, which is what a language switcher shows:
# a reader looking for Dutch scans for "Nederlands", not for "Dutch". MediaWiki ships a full
# table for this; a project this size only needs the locales it actually enables, so entries
# are added alongside the translation rather than up front. An unlisted code falls back to
# the code itself, which is ugly but honest.
_AUTONYMS = {
    'en': 'English',
    'nl': 'Nederlands',
    'qqx': 'qqx (message keys)',
}


def language_name(locale: str) -> str:
    """The language's own name for ``locale``, for a language switcher."""
    return _AUTONYMS.get(locale, locale)


_MESSAGES: dict[str, dict[str, str]] = {}
_PLURAL_RE = re.compile(r'\{\{PLURAL:\$(\d+)\|([^}]*)\}\}')
_MISSING_L, _MISSING_R = '⧼', '⧽'   # ⧼key⧽ — loud marker for a missing message


def load(directory: str = _I18N_DIR) -> None:
    """(Re)load every ``<code>.json`` locale file from ``directory``. Called at import.

    Skips ``qqq.json`` (documentation) and the per-file ``@metadata`` object. A malformed
    or unreadable file is skipped rather than crashing startup.
    """
    _MESSAGES.clear()
    if not os.path.isdir(directory):
        return
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith('.json') or filename == 'qqq.json':
            continue
        code = filename[:-5]
        try:
            with open(os.path.join(directory, filename), encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            _MESSAGES[code] = {
                k: v for k, v in data.items()
                if k != '@metadata' and isinstance(v, str)
            }
    # Fail closed: a translation is compared with its English, so with no English, or for a
    # key English does not have, nothing is served.
    source = _MESSAGES.get(SOURCE_LOCALE)
    _REFUSED.clear()
    for code, messages in _MESSAGES.items():
        if code == SOURCE_LOCALE:
            continue
        refused = sorted(
            key for key, text in messages.items()
            if source is None or key not in source or not markup_is_permitted(text, source[key])
        )
        for key in refused:
            del messages[key]
        if refused:
            _REFUSED[code] = refused


# ── Markup in translations ────────────────────────────────────────────────────────────
#
# Some messages carry inline HTML, and both consumers render it as HTML: the SPA through
# banana-i18n into innerHTML (richHtml), and error_pages.py's `hint`. English is ours;
# translations are not — they arrive from translatewiki, typed by volunteers. banana-i18n
# is not a sanitiser: a self-closing tag written without a space before `/>` keeps its
# attributes, and inside a {{PLURAL:}}, {{GENDER:}} or {{GRAMMAR:}} branch any HTML passes
# through untouched. Text it cannot parse — a stray `<`, tags that do not nest, an unclosed
# `{{` — makes it throw, and msg() then shows the message key instead of any text.
#
# So a translation is served only if it parses the way banana-i18n needs, and uses only
# markup its English original uses: the same tag names with the same attributes and
# attribute values, as many times as it likes, in any order (a language may need a bold
# number in each plural branch). Anything else is not served, and English is used for that
# one message. With no English to compare against, no translation is served at all.
# tests/test_i18n.py applies the same check to every delivered file, so a bad translation
# fails CI where it arrives.
#
# The patterns are written so that no input makes them backtrack: a tag must start `<name`
# or `</name` with no whitespace, and each part of an attribute list starts with a distinct
# character.

_TAG_RE = re.compile(r'<(/?)([A-Za-z][A-Za-z0-9-]*)((?:[^<>"\']|"[^"]*"|\'[^\']*\')*)>')
_ATTR_RE = re.compile(r'([^\s=/"\'<>]+)(?:\s*=\s*("[^"]*"|\'[^\']*\'|[^\s"\'>]+))?')
_FUNCTION_RE = re.compile(r'\{\{([A-Za-z]+):')
_FUNCTIONS = {'PLURAL', 'GENDER', 'GRAMMAR'}

_REFUSED: dict[str, list[str]] = {}


def _unquote(value: str) -> str:
    """Remove the one pair of quotes around an attribute value, and nothing more."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        return value[1:-1]
    return value


def markup_signature(text: str) -> set[tuple] | None:
    """The distinct tags ``text`` uses, each with its attributes and their values.

    ``None`` when banana-i18n could not parse the text: a ``<`` that does not start a tag,
    tags that do not nest, a self-closing tag, attributes on a closing tag, or ``{{`` that
    does not open a closed PLURAL, GENDER or GRAMMAR.
    """
    tags = set()
    open_tags: list[str] = []
    for match in _TAG_RE.finditer(text):
        closing, name, rest = match.groups()
        name, rest = name.lower(), rest.rstrip()
        if rest.endswith('/'):
            return None
        if closing:
            if rest or not open_tags or open_tags.pop() != name:
                return None
        else:
            open_tags.append(name)
        attrs = tuple(sorted(
            (attr.lower(), _unquote(value or '')) for attr, value in _ATTR_RE.findall(rest)
        ))
        tags.add((closing, name, attrs))
    if open_tags or '<' in _TAG_RE.sub('', text):
        return None
    functions = _FUNCTION_RE.findall(text)
    if text.count('{{') != len(functions) or text.count('}}') != len(functions):
        return None
    if any(function.upper() not in _FUNCTIONS for function in functions):
        return None
    return tags


def _describe(tag: tuple) -> str:
    closing, name, attrs = tag
    rendered = ''.join(f' {attr}="{value}"' for attr, value in attrs)
    return f'<{closing}{name}{rendered}>'


def markup_problem(translation: str, english: str) -> str | None:
    """Why ``translation`` may not be served in place of ``english``, or ``None`` if it may."""
    allowed = markup_signature(english)
    if allowed is None:
        return 'its English cannot be parsed, so there is nothing to compare it with'
    used = markup_signature(translation)
    if used is None:
        return ('it cannot be parsed: a "<" that does not start a tag, tags that do not '
                'nest, a self-closing tag, or an unclosed or unknown {{...}}')
    extra = used - allowed
    if extra:
        return 'it adds markup its English does not have: ' + ', '.join(sorted(map(_describe, extra)))
    return None


def markup_is_permitted(translation: str, english: str) -> bool:
    """True when ``translation`` may be served in place of ``english``."""
    return markup_problem(translation, english) is None


def refused_translations() -> dict[str, list[str]]:
    """{locale: [keys]} not served by the last load(), for the app to log once it can."""
    return {code: list(keys) for code, keys in _REFUSED.items()}


def log_refusals(logger) -> None:
    """Report what load() refused. Called by the app after logging is configured."""
    if SOURCE_LOCALE not in _MESSAGES and any(code != SOURCE_LOCALE for code in _MESSAGES):
        logger.error('i18n: %s.json did not load, so no translation is being served',
                     SOURCE_LOCALE)
    for code, keys in _REFUSED.items():
        logger.warning('i18n: %s.json: not serving %d message(s) that fail the markup '
                       'check: %s', code, len(keys), ', '.join(keys))


def has_locale(locale: str) -> bool:
    return locale in _MESSAGES


def text_direction(locale: str) -> str:
    """'rtl' for right-to-left languages, else 'ltr' (matched on the base language subtag)."""
    return 'rtl' if (locale or '').split('-')[0].lower() in _RTL_LANGS else 'ltr'


def _plural_index(n: int, locale: str) -> int:
    """Index into a ``{{PLURAL:...}}`` form list for count ``n``.

    v1 implements the English/Germanic rule (n == 1 -> form 0, else form 1), which is
    exact for the only shipped locale (en). Locales with other plural categories
    (ar, ru, pl, cy, ...) need CLDR rules before being enabled — a tracked follow-up;
    banana-i18n already applies CLDR rules on the client side.
    """
    return 0 if n == 1 else 1


def _expand_plural(text: str, params, locale: str) -> str:
    def _repl(match):
        idx = int(match.group(1)) - 1
        forms = match.group(2).split('|')
        try:
            n = int(params[idx])
        except (IndexError, ValueError, TypeError):
            n = 0
        i = _plural_index(n, locale)
        if not forms:
            return ''
        return forms[i] if i < len(forms) else forms[-1]
    return _PLURAL_RE.sub(_repl, text)


def _substitute(text: str, params) -> str:
    # Replace $2 before $1 would be wrong via naive ordering; replace high indices first.
    for i in range(len(params), 0, -1):
        text = text.replace(f'${i}', str(params[i - 1]))
    return text


def resolve(key: str, locale: str = SOURCE_LOCALE, params=()) -> str:
    """Resolve ``key`` to text in ``locale``.

    Fallback chain: ``locale`` -> ``en``. Missing everywhere -> ``⧼key⧽`` (loud). The
    ``qqx`` debug locale returns ``(key)``. ``params`` are 1-indexed as ``$1..$n``;
    ``{{PLURAL:$n|a|b}}`` selects a form from the count in ``$n``.
    """
    if locale == DEBUG_LOCALE:
        return f'({key})'
    text = _MESSAGES.get(locale, {}).get(key)
    if text is None and locale != SOURCE_LOCALE:
        text = _MESSAGES.get(SOURCE_LOCALE, {}).get(key)
    if text is None:
        return f'{_MISSING_L}{key}{_MISSING_R}'
    params = tuple(params)
    if '{{PLURAL:' in text:
        text = _expand_plural(text, params, locale)
    if params:
        text = _substitute(text, params)
    return text


def all_messages(locale: str) -> dict[str, str]:
    """Full message map for ``locale`` (English-filled for fallback), for the client-side
    banana-i18n island. ``qqx`` maps every key to ``(key)`` so the JS surface is also
    coverage-checkable.

    NOTE: v1 ships the whole map inline per page. When the JS message set grows, switch to a
    cache-headered per-locale endpoint (like the static ``?v=<sha>`` scheme).
    """
    en = _MESSAGES.get(SOURCE_LOCALE, {})
    if locale == DEBUG_LOCALE:
        return {k: f'({k})' for k in en}
    # Project onto English's key set rather than dict.update()-ing the locale over it: a
    # translation may still hold a message the source has since dropped (translatewiki keeps
    # translating until it next syncs), and update() would serve that stale message to the
    # client. English is the definition of what exists; a translation only supplies values.
    # This is also what lets a key be deleted from en.json without waiting for translatewiki
    # to catch up -- the stale entry becomes inert instead of leaking.
    translated = _MESSAGES.get(locale, {})
    return {key: translated.get(key, text) for key, text in en.items()}


load()
