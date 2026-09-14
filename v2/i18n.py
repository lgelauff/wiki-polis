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
import logging
import os
import re

_log = logging.getLogger(__name__)

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
    source = _MESSAGES.get(SOURCE_LOCALE, {})
    for code, messages in _MESSAGES.items():
        if code == SOURCE_LOCALE:
            continue
        refused = [k for k, v in messages.items() if k in source and not markup_is_permitted(v, source[k])]
        for key in refused:
            del messages[key]
        if refused:
            _log.warning('i18n: %s.json: not serving %d message(s) whose markup differs from '
                         'English: %s', code, len(refused), ', '.join(sorted(refused)))


# ── Markup in translations ────────────────────────────────────────────────────────────
#
# Some messages carry inline HTML, and both consumers render it as HTML: the SPA through
# banana-i18n into innerHTML (richHtml), and error_pages.py's `hint`. English is ours;
# translations are not — they arrive from translatewiki, typed by volunteers. banana-i18n
# is not a sanitiser: a self-closing tag keeps its attributes (`<img src=x onerror=…/>`),
# and inside a {{PLURAL:}}, {{GENDER:}} or {{GRAMMAR:}} branch any HTML passes through
# untouched. A stray `<` makes it throw, which blanks the page it renders on.
#
# So a translation may only use markup its English original already uses: the same tag
# names with the same attributes and attribute values, as many times as it likes, in any
# order (a language may need a bold number in each plural branch). Anything else is not
# served, and English is used for that one message. tests/test_i18n.py applies the same
# check to every delivered file, so a bad translation fails CI where it arrives rather than
# being quietly replaced in production.

_TAG_RE = re.compile(r'<\s*(/?)\s*([A-Za-z][A-Za-z0-9-]*)((?:[^<>"\']|"[^"]*"|\'[^\']*\')*)>')
_ATTR_RE = re.compile(r'([^\s=/"\'<>]+)(?:\s*=\s*("[^"]*"|\'[^\']*\'|[^\s"\'>]+))?')


def markup_signature(text: str) -> set[tuple] | None:
    """The distinct tags ``text`` uses, each with its attributes and their values.

    ``None`` when the text holds a ``<`` that is not part of a tag, which banana-i18n
    cannot parse — that is a defect in its own right, not a signature.
    """
    tags = set()
    for match in _TAG_RE.finditer(text):
        closing, name, rest = match.groups()
        attrs = tuple(sorted(
            (attr.lower(), (value or '').strip('"\''))
            for attr, value in _ATTR_RE.findall(rest.rstrip().rstrip('/'))
        ))
        tags.add((closing, name.lower(), attrs))
    if '<' in _TAG_RE.sub('', text):
        return None
    return tags


def markup_is_permitted(translation: str, english: str) -> bool:
    """True when ``translation`` uses no markup that ``english`` does not."""
    allowed = markup_signature(english)
    used = markup_signature(translation)
    return allowed is not None and used is not None and used <= allowed


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
