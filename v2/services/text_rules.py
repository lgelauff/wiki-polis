"""One rule for plain text people type: how it is cleaned, stored and counted (#616).

Text is stored as typed, never HTML-escaped: "<", "&" and quotes are kept and count as one
character each. Escaping happens where the text is shown (React does it by default), not
here. Cleaning only removes what a reader cannot see or what can disguise the text:

* NFC normalisation (never NFKC, which changes what was typed);
* CRLF, lone CR, VT, FF, NEL and U+2028/U+2029 become a newline (Word and PowerPoint
  paste some of these between lines);
* control characters other than newline and tab, DEL, C1 controls, U+2028/U+2029, lone
  surrogates, noncharacters and U+FEFF (byte order mark) are removed;
* the bidi embedding, override and isolate characters U+202A–U+202E and U+2066–U+2069
  (the "Trojan Source" pattern) are removed;
* whitespace around the text is stripped.

LRM/RLM/ALM, ZWJ/ZWNJ and variation selectors stay: emoji and several scripts need them.

Removing the isolates is a trade-off: balanced pairs are legitimate in mixed-direction
text, and without them such text can show its parts in a different order. They are
removed anyway because, like the overrides, they can make text read differently from
what is stored. LRM/RLM, which stay, cover most mixed-direction needs.

A character is what a reader sees as one: an extended grapheme cluster (UAX #29), counted
with the `regex` package's ``\\X``. The browser counts the same way with Intl.Segmenter
(frontend/src/text-rules.ts); both are tested against frontend/src/text-rules-cases.json.
The server has the final say. Two hidden caps keep storage safe whatever the clusters:
at most 1000 code points in all (also Polis's own comment limit), and at most
MAX_CLUSTER_CODE_POINTS in one cluster (so "e" plus fifty combining marks is refused).
"""
from __future__ import annotations

import re
import unicodedata

import regex

MAX_CHARACTERS = 280
STORAGE_CODE_POINTS = 1000
MAX_CLUSTER_CODE_POINTS = 30

_REMOVED = re.compile(
    '['
    '\x00-\x08\x0e-\x1f\x7f-\x84\x86-\x9f'  # C0 but tab and line breaks, DEL, C1 but NEL
    '\ufeff'                                # byte order mark
    '\u202a-\u202e\u2066-\u2069'            # bidi embeddings, overrides and isolates
    '\ud800-\udfff'                         # lone surrogates
    '\ufdd0-\ufdef'                         # noncharacters
    ']'
    # U+nFFFE and U+nFFFF in every plane are noncharacters too.
    '|[\ufffe\uffff\U0001fffe\U0001ffff\U0002fffe\U0002ffff\U0003fffe\U0003ffff'
    '\U0004fffe\U0004ffff\U0005fffe\U0005ffff\U0006fffe\U0006ffff\U0007fffe\U0007ffff'
    '\U0008fffe\U0008ffff\U0009fffe\U0009ffff\U000afffe\U000affff\U000bfffe\U000bffff'
    '\U000cfffe\U000cffff\U000dfffe\U000dffff\U000efffe\U000effff\U000ffffe\U000fffff'
    '\U0010fffe\U0010ffff]'
)
_LINE_BREAK = re.compile('\r\n|[\r\x0b\x0c\x85\u2028\u2029]')
_CLUSTER = regex.compile(r'\X')


def clean_text(value: str | None) -> str:
    """The text as it is stored and shown: see the module docstring."""
    text = _LINE_BREAK.sub('\n', value or '')
    text = _REMOVED.sub('', text)
    return unicodedata.normalize('NFC', text).strip()


def count_characters(text: str) -> int:
    """User-perceived characters (extended grapheme clusters) in already-cleaned text."""
    return len(_CLUSTER.findall(text))


def fits(text: str, max_characters: int = MAX_CHARACTERS) -> bool:
    """True when cleaned, non-empty ``text`` is within ``max_characters`` characters and the
    hidden storage caps."""
    if not text or len(text) > STORAGE_CODE_POINTS:
        return False
    clusters = _CLUSTER.findall(text)
    return (len(clusters) <= max_characters
            and all(len(cluster) <= MAX_CLUSTER_CODE_POINTS for cluster in clusters))


def clean_note(value: str | None, limit: int = STORAGE_CODE_POINTS) -> str:
    """Cleaned free text for staff notes and flag details, cut to ``limit`` code points
    without splitting a character."""
    text = clean_text(value)
    if len(text) <= limit:
        return text
    kept, used = [], 0
    for cluster in _CLUSTER.findall(text):
        if used + len(cluster) > limit:
            break
        kept.append(cluster)
        used += len(cluster)
    return ''.join(kept).rstrip()
