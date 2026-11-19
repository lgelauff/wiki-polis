"""The arrival banner (the space-mismatch warning, #293) fits a 320 px screen.

Its text kept one long link on a single line and its button sat beside it, so at 320 px the
banner was 359 px wide and the page scrolled sideways. jsdom applies no stylesheet, so the
vitest suite cannot see this; this reads style.css.
"""

from pathlib import Path

import tinycss2

STYLE_CSS = Path(__file__).resolve().parents[1] / 'static' / 'style.css'


def _rules():
    """{selector: declarations} for every top-level rule in style.css (later rules win)."""
    rules = {}
    for node in tinycss2.parse_stylesheet(
        STYLE_CSS.read_text(encoding='utf-8'), skip_comments=True, skip_whitespace=True,
    ):
        if node.type != 'qualified-rule':
            continue
        declarations = {
            decl.lower_name: tinycss2.serialize(decl.value).strip()
            for decl in tinycss2.parse_declaration_list(
                node.content, skip_comments=True, skip_whitespace=True,
            )
            if decl.type == 'declaration'
        }
        for selector in tinycss2.serialize(node.prelude).split(','):
            rules.setdefault(' '.join(selector.split()), {}).update(declarations)
    return rules


def test_banner_wraps_its_button_below_the_text():
    assert _rules()['.space-warn'].get('flex-wrap') == 'wrap'


def test_banner_text_can_shrink_and_break():
    text = _rules()['.space-warn > span']
    assert text.get('min-width') == '0'
    assert text.get('overflow-wrap') in ('anywhere', 'break-word')


def test_banner_link_is_not_kept_on_one_line():
    rules = _rules()
    for selector in ('.space-warn a', '.space-warn > span'):
        assert rules.get(selector, {}).get('white-space') != 'nowrap', selector


def test_banner_uses_logical_sides_for_right_to_left():
    rules = _rules()
    for selector in ('.space-warn', '.space-warn--real', '.space-warn--demo', '.space-warn-ok'):
        physical = [p for p in rules[selector] if p.endswith(('-left', '-right'))]
        assert not physical, f'{selector} sets {physical}; use the -inline-start/-end form'
