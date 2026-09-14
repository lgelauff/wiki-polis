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
_PLURAL_RE = re.compile(r'\{\{PLURAL:\$(\d+)\|([^}]*)\}\}', re.IGNORECASE | re.ASCII)
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
    # Fail closed: a translation is compared with its English, so with no English nothing is
    # served. A key English no longer has is stale rather than wrong -- translatewiki drops it
    # on its next export -- so it is set aside separately and not reported as a failure.
    source = _MESSAGES.get(SOURCE_LOCALE)
    _REFUSED.clear()
    _STALE.clear()
    for code, messages in _MESSAGES.items():
        if code == SOURCE_LOCALE:
            continue
        refused, stale = {}, []
        for key, text in messages.items():
            if source is None:
                refused[key] = f'{SOURCE_LOCALE}.json did not load'
            elif key not in source:
                stale.append(key)
            elif (problem := markup_problem(text, source[key])) is not None:
                refused[key] = problem
        for key in [*refused, *stale]:
            del messages[key]
        if refused:
            _REFUSED[code] = dict(sorted(refused.items()))
        if stale:
            _STALE[code] = sorted(stale)


# ── Markup in translations ────────────────────────────────────────────────────────────
#
# Some messages carry inline HTML, and both consumers render it as HTML: the SPA through
# banana-i18n into innerHTML (richHtml), and error_pages.py's `hint`. English is ours;
# translations are not — they arrive from translatewiki, typed by volunteers. banana-i18n
# is not a sanitiser: a self-closing tag written without a space before `/>` keeps its
# attributes, and inside a {{PLURAL:}}, {{GENDER:}} or {{GRAMMAR:}} branch any HTML passes
# through untouched. Text its parser rejects makes it throw, and msg() then shows the message
# key instead of any text.
#
# So a message is scanned against a deliberately small grammar, and a translation is served
# only if it fits that grammar and uses only markup its English original uses: the same tag
# names with the same attributes and values, as many times as it likes, in any order (a
# language may need a bold number in each plural branch). Anything else is not served, and
# English is used for that one message. With no English to compare against, no translation
# is served at all. tests/test_i18n.py applies the same check to every delivered file, and
# frontend/src/i18n/catalogue-parses.test.ts runs every message through banana itself.
#
# banana-i18n only runs its full parser when a message contains `{{` or `<`; anything else is
# plain text with $n placeholders, and is accepted as it is. The grammar below is a strict
# subset of what the full parser accepts. The scan is linear in the message's length: nesting
# is capped, and each character is read a bounded number of times.

_NAME_START = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
_NAME_CHARS = _NAME_START | frozenset('0123456789')
_ATTR_CHARS = _NAME_CHARS | frozenset('-')
_SPACE = frozenset(' \t\n')
_DIGITS = frozenset('0123456789')   # banana's /\d/; str.isdigit() also takes '²' and '①'
_FUNCTIONS = {'PLURAL', 'GENDER', 'GRAMMAR'}

_PLACEHOLDER_RE = re.compile(r'\$(\d+)', re.ASCII)
_EXPLICIT_FORM_RE = re.compile(r'\d=')

_REFUSED: dict[str, dict[str, str]] = {}
_STALE: dict[str, list[str]] = {}


class _Unparseable(ValueError):
    """Text outside the grammar, with the reason and the offset where scanning stopped."""


class _Scanner:
    """A recursive-descent reader for the markup grammar. Each method consumes from ``pos``.

    message  := node*
    node     := text | placeholder | element | function
    text     := any character except < > { } | \\ and a $ not followed by a digit
    element  := '<' name (space+ attr)* space* '>' node* '</' name space* '>'
    attr     := attrname space* '=' space* ( '"' value '"' | "'" value "'" )
    function := '{{' FUNCTION ':' ( '$' digits | word ) ( '|' node+ )+ '}}'   (one general form)

    A top-level '|' is ordinary text; inside a function it separates branches. Every element
    closes within the branch or message that opened it.
    """

    _MAX_DEPTH = 20   # nesting deeper than any real message; also keeps recursion bounded

    def __init__(self, text: str):
        self.text, self.pos, self.tags, self.depth = text, 0, set(), 0

    def fail(self, reason: str):
        raise _Unparseable(f'{reason} (at character {self.pos + 1})')

    def peek(self, token: str) -> bool:
        return self.text.startswith(token, self.pos)

    def nodes(self, in_function: bool) -> int:
        """Read nodes until the end of the text or, inside a function, a '|' or '}}'."""
        count = 0
        text = self.text
        while self.pos < len(text):
            char = text[self.pos]
            if in_function and (char == '|' or self.peek('}}')):
                break
            if self.peek('</'):
                break
            if char == '<':
                self.element(in_function)
            elif self.peek('{{'):
                self.function()
            elif char in '{}':
                self.fail('a "{" or "}" that is not part of {{...}}')
            elif char == '>':
                self.fail('a ">" that does not close a tag')
            elif char == '\\':
                self.fail('a backslash')
            elif char == '$':
                start = self.pos
                self.pos += 1
                while self.pos < len(text) and text[self.pos] in _DIGITS:
                    self.pos += 1
                if self.pos == start + 1:
                    self.pos = start
                    self.fail('a "$" that is not a placeholder like $1')
            else:
                self.pos += 1
            count += 1
        return count

    def name(self, chars=_NAME_CHARS) -> str:
        start = self.pos
        if self.pos >= len(self.text) or self.text[self.pos] not in _NAME_START:
            self.fail('a "<" that does not start a tag')
        while self.pos < len(self.text) and self.text[self.pos] in chars:
            self.pos += 1
        return self.text[start:self.pos].lower()

    def spaces(self) -> int:
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] in _SPACE:
            self.pos += 1
        return self.pos - start

    def enter(self):
        self.depth += 1
        if self.depth > self._MAX_DEPTH:
            self.fail('markup nested too deeply')

    def element(self, in_function: bool):
        self.enter()
        if self.pos + 1 >= len(self.text) or self.text[self.pos + 1] not in _NAME_START:
            self.fail('a "<" that does not start a tag')
        self.pos += 1                                   # '<'
        name = self.name()
        attrs = []
        while True:
            gap = self.spaces()
            if self.peek('>'):
                self.pos += 1
                break
            if self.peek('/'):
                self.fail('a self-closing tag')
            if not gap:
                self.fail(f'an attribute not separated from <{name}> by a space, or a malformed tag')
            attr = self.name(_ATTR_CHARS)
            self.spaces()
            if not self.peek('='):
                self.fail(f'attribute "{attr}" without a value')
            self.pos += 1
            self.spaces()
            quote = self.text[self.pos] if self.pos < len(self.text) else ''
            if quote not in ('"', "'"):
                self.fail(f'attribute "{attr}" with an unquoted value')
            end = self.text.find(quote, self.pos + 1)
            if end < 0:
                self.fail(f'attribute "{attr}" with an unclosed quote')
            value = self.text[self.pos + 1:end]
            if any(char in value for char in '<>{}\\'):
                self.fail(f'attribute "{attr}" with markup in its value')
            attrs.append((attr, value))
            self.pos = end + 1
        self.tags.add(('', name, tuple(sorted(attrs))))
        self.nodes(in_function)
        if not self.peek('</'):
            self.fail(f'<{name}> is not closed')
        self.pos += 2
        closing = self.name()
        self.spaces()
        if closing != name or not self.peek('>'):
            self.fail(f'</{closing}> does not close <{name}>')
        self.pos += 1
        self.tags.add(('/', name, ()))
        self.depth -= 1

    def function(self):
        self.enter()
        self.pos += 2                                   # '{{'
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] in _NAME_START:
            self.pos += 1
        function = self.text[start:self.pos]
        if function.upper() not in _FUNCTIONS or not self.peek(':'):
            self.fail('a {{...}} that is not PLURAL, GENDER or GRAMMAR')
        self.pos += 1
        start = self.pos
        if function.upper() == 'GRAMMAR':
            while self.pos < len(self.text) and self.text[self.pos] in _NAME_START:
                self.pos += 1
        elif self.peek('$'):
            self.pos += 1
            while self.pos < len(self.text) and self.text[self.pos] in _DIGITS:
                self.pos += 1
            if self.pos == start + 1:
                self.pos = start
        if self.pos == start or not self.peek('|'):
            self.fail(f'{{{{{function}:...}}}} whose argument is not a placeholder like $1 directly followed by "|"')
        general_forms = 0
        while self.peek('|'):
            self.pos += 1
            branch = self.pos
            if not self.nodes(in_function=True):
                self.fail(f'an empty branch in {{{{{function}:...}}}}')
            # banana treats any branch containing "<digits>=" as an explicit form for one
            # number, and prints "undefined" for other numbers unless some branch is general.
            if not _EXPLICIT_FORM_RE.search(self.text, branch, self.pos):
                general_forms += 1
        if not general_forms:
            self.fail(f'{{{{{function}:...}}}} with only explicit forms like "2=..."')
        if not self.peek('}}'):
            self.fail(f'{{{{{function}:...}}}} is not closed')
        self.pos += 2
        self.depth -= 1


def _signature(text: str) -> set[tuple]:
    """The distinct tags ``text`` uses, with their attributes; raises _Unparseable."""
    if '<' not in text and '{{' not in text:
        return set()
    scanner = _Scanner(text)
    scanner.nodes(in_function=False)
    if scanner.pos != len(text):
        scanner.fail('a closing tag with no matching opening tag')
    return scanner.tags


def markup_signature(text: str) -> set[tuple] | None:
    """The distinct tags ``text`` uses, each with its attributes and their values, or ``None``
    when the text falls outside the markup grammar (see _Scanner)."""
    try:
        return _signature(text)
    except _Unparseable:
        return None


def _describe(tag: tuple) -> str:
    _closing, name, attrs = tag
    rendered = ''.join(f' {attr}="{value}"' for attr, value in attrs)
    return f'<{name}{rendered}>'


def markup_problem(translation: str, english: str) -> str | None:
    """Why ``translation`` may not be served in place of ``english``, or ``None`` if it may."""
    try:
        allowed = _signature(english)
    except _Unparseable as error:
        return f'its English cannot be checked: {error}'
    try:
        used = _signature(translation)
    except _Unparseable as error:
        return f'it cannot be parsed: {error}'
    extra = {tag for tag in used - allowed if tag[0] == ''}
    if extra:
        return 'it adds markup its English does not have: ' + ', '.join(sorted(map(_describe, extra)))
    placeholders = set(_PLACEHOLDER_RE.findall(translation)) - set(_PLACEHOLDER_RE.findall(english))
    if placeholders:
        return 'it uses placeholders its English does not have: ' + ', '.join(f'${n}' for n in sorted(placeholders, key=lambda n: (len(n), n)))
    return None


def markup_is_permitted(translation: str, english: str) -> bool:
    """True when ``translation`` may be served in place of ``english``."""
    return markup_problem(translation, english) is None


def refused_translations() -> dict[str, dict[str, str]]:
    """{locale: {key: reason}} not served by the last load(), for the app to log."""
    return {code: dict(reasons) for code, reasons in _REFUSED.items()}


def stale_translations() -> dict[str, list[str]]:
    """{locale: [keys]} set aside by the last load() because English no longer has them."""
    return {code: list(keys) for code, keys in _STALE.items()}


def log_refusals(logger) -> None:
    """Report what load() set aside. Called by the app after logging is configured."""
    if SOURCE_LOCALE not in _MESSAGES and any(code != SOURCE_LOCALE for code in _MESSAGES):
        logger.error('i18n: %s.json did not load, so no translation is being served',
                     SOURCE_LOCALE)
    for code, reasons in _REFUSED.items():
        logger.warning('i18n: %s.json: not serving %d message(s): %s', code, len(reasons),
                       '; '.join(f'{key}: {reason}' for key, reason in reasons.items()))
    for code, keys in _STALE.items():
        logger.info('i18n: %s.json: %d message(s) no longer in English, awaiting the next '
                    'translatewiki export: %s', code, len(keys), ', '.join(keys))


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


_PLACEHOLDER_RE = re.compile(r'\$(\d+)')


def _qqx(key: str, params=()) -> str:
    """``(key)``, or ``(key: p1, p2)`` with its parameters, as MediaWiki's qqx renders."""
    return f'({key}: {", ".join(str(p) for p in params)})' if params else f'({key})'


def qqx_message(key: str, english: str) -> str:
    """The qqx catalogue entry for a message: ``(key: $1, $2)`` for each placeholder the
    English uses, so a client substituting parameters shows them inside the parentheses."""
    count = max((int(n) for n in _PLACEHOLDER_RE.findall(english)), default=0)
    return _qqx(key, tuple(f'${n}' for n in range(1, count + 1)))


def resolve(key: str, locale: str = SOURCE_LOCALE, params=()) -> str:
    """Resolve ``key`` to text in ``locale``.

    Fallback chain: ``locale`` -> ``en``. Missing everywhere -> ``⧼key⧽`` (loud). The
    ``qqx`` debug locale returns ``(key)``, or ``(key: p1, p2)`` when parameters are passed,
    so what was interpolated stays visible. ``params`` are 1-indexed as ``$1..$n``;
    ``{{PLURAL:$n|a|b}}`` selects a form from the count in ``$n``.
    """
    if locale == DEBUG_LOCALE:
        return _qqx(key, tuple(params))
    text = _MESSAGES.get(locale, {}).get(key)
    if text is None and locale != SOURCE_LOCALE:
        text = _MESSAGES.get(SOURCE_LOCALE, {}).get(key)
    if text is None:
        return f'{_MISSING_L}{key}{_MISSING_R}'
    params = tuple(params)
    if _PLURAL_RE.search(text):
        text = _expand_plural(text, params, locale)
    if params:
        text = _substitute(text, params)
    return text


def all_messages(locale: str) -> dict[str, str]:
    """Full message map for ``locale`` (English-filled for fallback), for the client-side
    banana-i18n island. ``qqx`` maps every key to ``(key)``, or ``(key: $1, $2)`` for one with
    parameters, so the JS surface is also coverage-checkable.

    NOTE: v1 ships the whole map inline per page. When the JS message set grows, switch to a
    cache-headered per-locale endpoint (like the static ``?v=<sha>`` scheme).
    """
    en = _MESSAGES.get(SOURCE_LOCALE, {})
    if locale == DEBUG_LOCALE:
        return {k: qqx_message(k, v) for k, v in en.items()}
    # Project onto English's key set rather than dict.update()-ing the locale over it: a
    # translation may still hold a message the source has since dropped (translatewiki keeps
    # translating until it next syncs), and update() would serve that stale message to the
    # client. English is the definition of what exists; a translation only supplies values.
    # This is also what lets a key be deleted from en.json without waiting for translatewiki
    # to catch up -- the stale entry becomes inert instead of leaking.
    translated = _MESSAGES.get(locale, {})
    return {key: translated.get(key, text) for key, text in en.items()}


load()
