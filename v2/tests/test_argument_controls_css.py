"""The two ways through step 1 of argument mapping look like equal buttons (GitHub #461),
and the colour tokens the progress-circle contrast test uses match style.css (#464).

"Add your argument …" was a dashed box in muted text and "Nothing to add" a borderless link,
so participants did not see either as something to press, or skipping as a choice. jsdom
applies no stylesheet, so the vitest suite cannot see this; this reads style.css.
"""

import re
from pathlib import Path

import tinycss2

V2 = Path(__file__).resolve().parents[1]
STYLE_CSS = V2 / 'static' / 'style.css'
PANEL_TEST = V2 / 'frontend' / 'src' / 'features' / 'legacy' / 'argument-mapping-panel.test.tsx'
ADD = '.at-contribute--idle'
SKIP = '.at-direct-skip'
# Every class the two idle buttons carry (argument-mapping-panel.tsx, Contribution).
BUTTON_CLASSES = ('.at-contribute', ADD, '.contribute-affordance', SKIP, '.contribute-direct-skip')
LOOK = {'border', 'border-color', 'border-style', 'border-width', 'background', 'background-color', 'color'}


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


def _resting_target(selector: str) -> bool:
    """Whether the selector's last compound picks out one of the buttons in its resting state
    (no :hover, :focus-visible, :disabled …)."""
    last = re.split(r'\s+|>|\+|~', selector.strip())[-1]
    if ':' in last:
        return False
    classes = re.findall(r'\.[\w-]+', last)
    return any(cls in BUTTON_CLASSES for cls in classes)


def test_add_and_nothing_to_add_share_one_button_style():
    """One rule styles both, so neither can drift back to a lesser look on its own."""
    shared = [declarations for selectors, declarations in _rules()
              if ADD in selectors and SKIP in selectors]

    assert shared, f'no rule styles {ADD} and {SKIP} together'
    style = shared[0]
    assert 'solid' in style.get('border', ''), 'a button has a solid edge, not a dashed or no border'
    assert style.get('background') not in (None, 'transparent', 'none')
    assert style.get('cursor') == 'pointer'


def _root_tokens() -> dict:
    return next(declarations for selectors, declarations in _rules() if selectors == [':root'])


def _rgb(value: str, tokens: dict, under=(255, 255, 255)) -> tuple[float, float, float]:
    """A CSS colour as sRGB 0-255: #rrggbb, var(--token), or rgba() laid over `under`."""
    value = value.strip()
    token = re.fullmatch(r'var\((--[\w-]+)\)', value)
    if token:
        return _rgb(tokens[token.group(1)], tokens, under)
    if re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    rgba = re.fullmatch(r'rgba?\(([^)]*)\)', value)
    assert rgba, f'unreadable colour {value!r}'
    parts = [float(part) for part in re.split(r'[\s,/]+', rgba.group(1).strip()) if part]
    alpha = parts[3] if len(parts) > 3 else 1.0
    return tuple(alpha * parts[i] + (1 - alpha) * under[i] for i in range(3))


def _contrast(first, second) -> float:
    def luminance(rgb):
        channels = [c / 255 for c in rgb]
        channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_the_idle_buttons_edge_stands_out_from_the_fill_and_the_page():
    """WCAG 1.4.11: the edge is what makes the idle buttons read as buttons, so it needs
    3:1 against the button's own fill and the page behind it. A faint tint failed this."""
    tokens = _root_tokens()
    style = next(declarations for selectors, declarations in _rules()
                 if ADD in selectors and SKIP in selectors)
    edge = style.get('border-color') or re.sub(r'^\S+\s+\S+\s+', '', style['border'])
    fill = _rgb(style['background'], tokens)
    for name, behind in (('the button fill', fill), ('the page', _rgb(tokens['--bg'], tokens))):
        ratio = _contrast(_rgb(edge, tokens, behind), behind)
        assert ratio >= 3, f'idle button edge {edge} is {ratio:.2f}:1 against {name}'


def test_no_other_rule_gives_either_button_its_own_resting_look():
    """Apart from the shared rule, no rule on any class the buttons carry, however it is
    qualified, sets an edge, fill or text colour for the resting state (hover, focus and
    disabled may). The old dashed green/red box came from such a rule."""
    for selectors, declarations in _rules():
        if ADD in selectors and SKIP in selectors:
            continue
        clash = LOOK & declarations.keys()
        for selector in selectors:
            assert not (clash and _resting_target(selector)), (
                f'{selector} restyles an idle argument button on its own: {sorted(clash)}'
            )


def test_the_circle_contrast_test_uses_the_colours_style_css_defines():
    """The vitest contrast check copies :root colours (vite will not serve style.css to it).
    A changed token must change the copy too, or that test checks stale colours."""
    root = next(declarations for selectors, declarations in _rules() if selectors == [':root'])
    table = re.search(r'const TOKENS[^{]*\{(.*?)\};', PANEL_TEST.read_text(encoding='utf-8'), re.S)
    assert table, 'no TOKENS table in the panel test'
    copied = dict(re.findall(r"'(--[\w-]+)':\s*'(#[0-9a-fA-F]{6})'", table.group(1)))

    assert copied, 'the TOKENS table is empty'
    for name, value in copied.items():
        assert root.get(name, '').lower() == value.lower(), f'{name}: test has {value}, style.css {root.get(name)}'
