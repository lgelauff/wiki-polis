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
    merged = dict(en)
    merged.update(_MESSAGES.get(locale, {}))
    return merged


load()
