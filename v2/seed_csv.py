"""CSV parsing and validation for bulk seed statement import.

Stdlib-only — no Flask dependency so this can be unit-tested in isolation.
"""
import csv
import io
from dataclasses import dataclass, field

MAX_FILE_BYTES = 100 * 1024
MAX_ROWS       = 200   # max statements per bulk import (CSV upload and text-area paste)
MAX_TEXT_CHARS = 280

# Unicode codepoints stripped from every cell value before validation.
# Includes BOM, zero-width spaces/joiners, and BiDi control characters
# (U+202A–U+202E covers the RTL override U+202E; U+2066–U+2069 are isolates).
_STRIP_CODEPOINTS = frozenset([
    0x0000,                          # null (belt-and-suspenders; file-level check is primary)
    0x00AD,                          # soft hyphen
    0x200B, 0x200C, 0x200D,          # zero-width space/non-joiner/joiner
    0xFEFF,                          # BOM / zero-width no-break space
    0x200E, 0x200F,                  # LTR / RTL marks
    *range(0x202A, 0x202F),          # LTR/RTL embedding and override controls
    *range(0x2066, 0x206A),          # BiDi isolate controls
])

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
    row: int       # 1-based; row 1 is the header, data starts at row 2
    reason: str
    limit_skipped: bool = False  # True when row was cut by MAX_ROWS limit


@dataclass
class ParseResult:
    texts:  list[str]      = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def _strip_cell(value: str) -> str:
    """Strip invisible/dangerous Unicode and formula-injection prefixes."""
    cleaned = ''.join(ch for ch in value if ord(ch) not in _STRIP_CODEPOINTS)
    while cleaned and cleaned[0] in _FORMULA_PREFIXES:
        cleaned = cleaned[1:]
    return cleaned.strip()


def parse_csv_bytes(raw: bytes) -> ParseResult:
    """Parse and validate a CSV byte string.

    Whole-file problems raise ValueError with a human-readable message.
    Row-level problems are collected into ParseResult.errors.

    Caller is responsible for enforcing the byte-length limit before calling
    (the route reads at most MAX_FILE_BYTES+1 bytes), but we double-check here.
    """
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError(f'File exceeds {MAX_FILE_BYTES // 1024} KB limit.')

    if b'\x00' in raw:
        raise ValueError('File contains null bytes and cannot be parsed.')

    try:
        text = raw.decode('utf-8-sig')   # strips UTF-8 BOM if present
    except UnicodeDecodeError:
        raise ValueError('File must be UTF-8 encoded. Re-save as UTF-8 and try again.')

    try:
        reader = csv.reader(io.StringIO(text, newline=''))
        rows   = list(reader)
    except csv.Error as exc:
        raise ValueError(f'CSV parse error: {exc}')

    if not rows:
        raise ValueError('File is empty.')

    header = [col.strip().lower() for col in rows[0]]
    if 'text' not in header:
        raise ValueError(
            f'Missing required "text" column. Found columns: {", ".join(rows[0]) or "(none)"}.'
        )
    text_idx = header.index('text')

    result = ParseResult()
    seen: set[str] = set()

    for raw_row_idx, row in enumerate(rows[1:], start=2):  # row 1 = header
        # An entirely empty CSV row (blank line) produces [] — treat as empty text
        if len(row) == 0 or (len(row) == 1 and row[0] == ''):
            result.errors.append(RowError(raw_row_idx, 'text is empty'))
            continue

        if len(row) <= text_idx:
            result.errors.append(RowError(raw_row_idx, 'missing "text" column value'))
            continue

        cell = _strip_cell(row[text_idx])

        if not cell:
            result.errors.append(RowError(raw_row_idx, 'text is empty'))
            continue

        if len(cell) > MAX_TEXT_CHARS:
            result.errors.append(RowError(
                raw_row_idx,
                f'text is too long ({len(cell)} characters; max {MAX_TEXT_CHARS})',
            ))
            continue

        if cell in seen:
            result.errors.append(RowError(raw_row_idx, 'duplicate — already added from an earlier row'))
            continue

        seen.add(cell)
        result.texts.append(cell)

        if len(result.texts) >= MAX_ROWS:
            # Count remaining rows as skipped
            for skipped_idx, _ in enumerate(rows[raw_row_idx:], start=raw_row_idx + 1):
                result.errors.append(RowError(
                    skipped_idx,
                    f'skipped — import limit of {MAX_ROWS} rows reached',
                    limit_skipped=True,
                ))
            break

    return result
