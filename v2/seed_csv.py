"""Shared validation constants and helpers for bulk seed statement import.

Stdlib-only — no Flask dependency so this can be unit-tested in isolation. The
bulk import is text-area only (the CSV upload was removed per the #236 review);
the textarea parser lives in app._parse_seed_text_lines and reuses these.
"""
from dataclasses import dataclass, field

MAX_FILE_BYTES = 100 * 1024
# Soft cap per bulk import. Deliberately low: a high cap signals that importing a
# large number of statements at once is desirable, which it isn't. There is no hard
# total cap — admins can run the import repeatedly — so this is a nudge, not a ceiling.
MAX_ROWS       = 20
MAX_TEXT_CHARS = 280

# Characters that, when leading a cell, trigger spreadsheet formula injection.
# Covers Excel/Sheets (=, +, -, @), LibreOffice Calc (| added), and tab/CR
# which some parsers treat as formula starters.
_FORMULA_PREFIXES = frozenset('=+-@|\t\r')


def strip_formula_prefixes(text: str) -> str:
    """Strip leading formula-injection characters from text."""
    while text and text[0] in _FORMULA_PREFIXES:
        text = text[1:]
    return text


@dataclass
class RowError:
    row: int       # 1-based source line number
    reason: str
    limit_skipped: bool = False  # True when row was cut by MAX_ROWS limit


@dataclass
class ParseResult:
    texts:  list[str]      = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
