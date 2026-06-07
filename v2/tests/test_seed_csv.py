"""Unit tests for seed_csv.parse_csv_bytes — no Flask context required."""
import pytest

from seed_csv import MAX_FILE_BYTES, MAX_ROWS, MAX_TEXT_CHARS, parse_csv_bytes


# ── Helpers ───────────────────────────────────────────────────────────────────

def _csv(*rows, header='text'):
    lines = [header] + list(rows)
    return '\n'.join(lines).encode('utf-8')


def _ok(raw, expected_texts):
    result = parse_csv_bytes(raw)
    assert result.texts == expected_texts
    assert result.errors == []


def _fail(raw, expected_msg_fragment):
    with pytest.raises(ValueError, match=expected_msg_fragment):
        parse_csv_bytes(raw)


# ── Whole-file rejection ──────────────────────────────────────────────────────

def test_empty_file():
    _fail(b'', 'empty')


def test_header_only_no_text_column():
    _fail(b'note\nsome note', '"text" column')


def test_header_only_with_text_column():
    result = parse_csv_bytes(b'text\n')
    assert result.texts == []
    assert result.errors == []


def test_null_bytes_in_file():
    _fail(b'text\nhello\x00world', 'null bytes')


def test_latin1_encoding():
    raw = 'text\nCaf\xe9'.encode('latin-1')
    _fail(raw, 'UTF-8')


def test_windows1252_encoding():
    # Bytes 0x93/0x94 are Windows-1252 curly quotes; not valid UTF-8
    raw = b'text\n\x93quoted\x94'
    _fail(raw, 'UTF-8')


def test_file_too_large():
    raw = b'text\n' + b'a' * (MAX_FILE_BYTES + 1)
    _fail(raw, 'exceeds')


def test_file_exactly_at_limit_is_accepted():
    # Build a file just at or under the limit
    padding = b'a' * (MAX_FILE_BYTES - len(b'text\n'))
    raw = b'text\n' + padding
    # May fail validation (too long row) but must not raise "exceeds" ValueError
    try:
        parse_csv_bytes(raw)
    except ValueError as exc:
        assert 'exceeds' not in str(exc)


# ── Encoding / Unicode ────────────────────────────────────────────────────────

def test_utf8_bom_stripped():
    raw = b'\xef\xbb\xbftext\nhello'
    _ok(raw, ['hello'])


def test_arabic_rtl():
    text = 'حرية المعرفة يجب أن تكون للجميع'
    _ok(_csv(text), [text])


def test_cjk():
    text = '维基媒体的使命是让知识自由'
    _ok(_csv(text), [text])


def test_emoji():
    text = 'Knowledge should be free 🌍📚'
    _ok(_csv(text), [text])


def test_mixed_scripts():
    text = 'Wikimedia (विकिमीडिया) est libre'
    _ok(_csv(text), [text])


def test_zero_width_space_stripped():
    raw = 'text\nhello​world'.encode('utf-8')
    result = parse_csv_bytes(raw)
    assert result.texts == ['helloworld']


def test_rtl_override_stripped():
    # U+202E is the RTL override character
    raw = 'text\nhello‮world'.encode('utf-8')
    result = parse_csv_bytes(raw)
    assert result.texts == ['helloworld']


def test_zero_width_joiner_stripped():
    raw = 'text\nhello‍world'.encode('utf-8')
    result = parse_csv_bytes(raw)
    assert result.texts == ['helloworld']


def test_bom_inside_cell_stripped():
    raw = 'text\nhello﻿world'.encode('utf-8')
    result = parse_csv_bytes(raw)
    assert result.texts == ['helloworld']


def test_cell_that_becomes_empty_after_stripping():
    # Only zero-width chars → treated as empty
    raw = 'text\n​‌'.encode('utf-8')
    result = parse_csv_bytes(raw)
    assert result.texts == []
    assert result.errors[0].row == 2
    assert 'empty' in result.errors[0].reason


# ── CSV format edge cases ─────────────────────────────────────────────────────

def test_windows_line_endings():
    raw = b'text\r\nhello\r\nworld'
    _ok(raw, ['hello', 'world'])


def test_old_mac_line_endings():
    raw = b'text\rhello\rworld'
    _ok(raw, ['hello', 'world'])


def test_quoted_cell_with_comma():
    raw = b'text\n"Yes, and also no."'
    _ok(raw, ['Yes, and also no.'])


def test_quoted_cell_with_embedded_double_quote():
    raw = b'text\n"She said ""free knowledge"""'
    _ok(raw, ['She said "free knowledge"'])


def test_quoted_cell_with_newline():
    raw = b'text\n"line one\nline two"'
    result = parse_csv_bytes(raw)
    # Imported; whitespace normalisation is the route's job, not the parser's
    assert len(result.texts) == 1
    assert 'line one' in result.texts[0]


def test_extra_columns_ignored():
    raw = b'text,note,extra\nhello,a note,ignored'
    _ok(raw, ['hello'])


def test_note_column_ignored():
    raw = b'text,note\nhello,some note'
    _ok(raw, ['hello'])


def test_header_case_insensitive():
    raw = b'Text\nhello'
    _ok(raw, ['hello'])


def test_missing_columns_in_row():
    raw = b'text,note\nhello\n,only note'
    result = parse_csv_bytes(raw)
    assert result.texts == ['hello']
    # Second data row has empty text after stripping
    assert any('empty' in e.reason for e in result.errors)


def test_semicolon_delimiter_rejected():
    raw = b'text;note\nhello;world'
    _fail(raw, '"text" column')


# ── Validation ────────────────────────────────────────────────────────────────

def test_empty_text_cell():
    raw = b'text\nhello\n\nworld'
    result = parse_csv_bytes(raw)
    assert result.texts == ['hello', 'world']
    assert result.errors[0].row == 3
    assert 'empty' in result.errors[0].reason


def test_whitespace_only_cell():
    raw = b'text\nhello\n   \nworld'
    result = parse_csv_bytes(raw)
    assert result.texts == ['hello', 'world']
    assert result.errors[0].row == 3


def test_text_exactly_max_length():
    text = 'a' * MAX_TEXT_CHARS
    _ok(_csv(text), [text])


def test_text_one_over_max_length():
    text = 'a' * (MAX_TEXT_CHARS + 1)
    result = parse_csv_bytes(_csv(text))
    assert result.texts == []
    assert result.errors[0].row == 2
    assert 'too long' in result.errors[0].reason
    assert str(MAX_TEXT_CHARS + 1) in result.errors[0].reason


def test_duplicate_within_file():
    raw = b'text\nhello\nhello\nworld'
    result = parse_csv_bytes(raw)
    assert result.texts == ['hello', 'world']
    assert result.errors[0].row == 3
    assert 'duplicate' in result.errors[0].reason


def test_case_different_not_duplicate():
    raw = b'text\nhello\nHello\nHELLO'
    result = parse_csv_bytes(raw)
    assert result.texts == ['hello', 'Hello', 'HELLO']
    assert result.errors == []


def test_max_rows_limit():
    rows = [f'Statement number {i}' for i in range(MAX_ROWS + 5)]
    raw = ('text\n' + '\n'.join(rows)).encode('utf-8')
    result = parse_csv_bytes(raw)
    assert len(result.texts) == MAX_ROWS
    skipped = [e for e in result.errors if 'limit' in e.reason]
    assert len(skipped) == 5


def test_exactly_max_rows_accepted():
    rows = [f'Statement number {i}' for i in range(MAX_ROWS)]
    raw = ('text\n' + '\n'.join(rows)).encode('utf-8')
    result = parse_csv_bytes(raw)
    assert len(result.texts) == MAX_ROWS
    assert result.errors == []


# ── Security ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('prefix', ['=', '+', '-', '@', '\t', '\r'])
def test_formula_injection_prefix_stripped(prefix):
    text = f'{prefix}CMD'
    raw = _csv(text)
    result = parse_csv_bytes(raw)
    assert result.texts == ['CMD']


def test_formula_prefix_only_becomes_empty():
    raw = _csv('=')
    result = parse_csv_bytes(raw)
    assert result.texts == []
    assert 'empty' in result.errors[0].reason


def test_multiple_formula_prefixes_stripped():
    raw = _csv('==+CMD')
    result = parse_csv_bytes(raw)
    assert result.texts == ['CMD']


def test_html_passes_through_unchanged():
    # XSS sanitisation is the route's responsibility (nh3); parser must not mangle it
    text = '<script>alert(1)</script>'
    raw = _csv(text)
    result = parse_csv_bytes(raw)
    assert result.texts == [text]


def test_url_not_fetched():
    text = 'http://internal-host/admin'
    _ok(_csv(text), [text])


def test_row_numbers_are_correct():
    raw = b'text\ngood\n\nbad_length_' + b'x' * 280 + b'\ngood2'
    result = parse_csv_bytes(raw)
    assert result.texts == ['good', 'good2']
    assert result.errors[0].row == 3   # empty row
    assert result.errors[1].row == 4   # too long
