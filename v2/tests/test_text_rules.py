"""The clean-text rule (#616), against the fixture the browser tests use too."""
import json
from pathlib import Path

import pytest

from services.text_rules import clean_note, clean_text, count_characters, fits

_CASES = json.loads(
    (Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'text-rules-cases.json')
    .read_text(encoding='utf-8')
)['cases']


def _expand(case, value):
    if 'append' in case:
        return value + case['append'] * case.get('repeat', 1)
    return value * case.get('repeat', 1)


@pytest.mark.parametrize('case', _CASES, ids=[case['name'] for case in _CASES])
def test_shared_cases(case):
    clean = clean_text(_expand(case, case['input']))
    assert clean == _expand(case, case['clean'])
    assert count_characters(clean) == case['characters']
    assert fits(clean) is case['fits']


def test_text_is_never_html_escaped():
    assert clean_text('<a href="x">&amp;</a>') == '<a href="x">&amp;</a>'


def test_lone_surrogate_from_json_is_removed():
    assert clean_text(json.loads('"a\\ud800b"')) == 'ab'


def test_clean_note_cuts_at_a_character_boundary():
    family = '\U0001F468\u200d\U0001F469\u200d\U0001F467\u200d\U0001F466'  # 7 code points
    note = clean_note('ab' + family * 2, limit=10)
    assert note == 'ab' + family
