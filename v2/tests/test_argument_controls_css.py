"""The two ways through step 1 of argument mapping look like equal buttons (GitHub #461).

"Add your argument …" was a dashed box in muted text and "Nothing to add" a borderless link,
so participants did not see either as something to press, or skipping as a choice. jsdom
applies no stylesheet, so the vitest suite cannot see this; this reads style.css.
"""

from pathlib import Path

import tinycss2

STYLE_CSS = Path(__file__).resolve().parents[1] / 'static' / 'style.css'
ADD = '.at-contribute--idle'
SKIP = '.at-direct-skip'


def _rules():
    """(selectors, declarations) for every top-level rule in style.css."""
    for node in tinycss2.parse_stylesheet(
        STYLE_CSS.read_text(encoding='utf-8'), skip_comments=True, skip_whitespace=True,
    ):
        if node.type != 'qualified-rule':
            continue
        selectors = [part.strip() for part in tinycss2.serialize(node.prelude).split(',')]
        declarations = {
            decl.lower_name: tinycss2.serialize(decl.value).strip()
            for decl in tinycss2.parse_declaration_list(
                node.content, skip_comments=True, skip_whitespace=True,
            )
            if decl.type == 'declaration'
        }
        yield selectors, declarations


def test_add_and_nothing_to_add_share_one_button_style():
    """One rule styles both, so neither can drift back to a lesser look on its own."""
    shared = [declarations for selectors, declarations in _rules()
              if ADD in selectors and SKIP in selectors]

    assert shared, f'no rule styles {ADD} and {SKIP} together'
    style = shared[0]
    assert 'solid' in style.get('border', ''), 'a button has a solid edge, not a dashed or no border'
    assert style.get('background') not in (None, 'transparent', 'none')
    assert style.get('cursor') == 'pointer'


def test_no_rule_gives_one_of_them_a_different_resting_look():
    """Apart from the shared rule, neither control's resting state sets its own edge,
    fill or text colour (hover, focus and disabled states may)."""
    look = {'border', 'border-color', 'border-style', 'background', 'color', 'font-size', 'font-weight'}
    for selectors, declarations in _rules():
        if ADD in selectors and SKIP in selectors:
            continue
        for selector in (ADD, SKIP):
            assert selector not in selectors or not look & declarations.keys(), (
                f'{selectors} restyles {selector} on its own: {sorted(look & declarations.keys())}'
            )
