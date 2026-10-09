"""The admin console's toast slot floats out of the flow (staging check, row actions).

A toast inserted above the heading pushed the rows down by its own height, so the pointer
that had just pressed "Mark as handled" landed on the next row's button. jsdom applies no
stylesheet, so the vitest suite cannot see where the slot sits; this reads console.css.
"""

from pathlib import Path

import tinycss2

CONSOLE_CSS = (Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'features'
               / 'admin' / 'console.css')


def _top_level_rules():
    return [
        node for node in tinycss2.parse_stylesheet(
            CONSOLE_CSS.read_text(encoding='utf-8'), skip_comments=True, skip_whitespace=True,
        )
        if node.type == 'qualified-rule'
    ]


def _declarations(selector: str) -> dict[str, str]:
    """The declarations of the top-level rule whose selector is exactly `selector`."""
    for rule in _top_level_rules():
        if tinycss2.serialize(rule.prelude).strip() == selector:
            return {
                decl.lower_name: tinycss2.serialize(decl.value).strip()
                for decl in tinycss2.parse_declaration_list(
                    rule.content, skip_comments=True, skip_whitespace=True,
                )
                if decl.type == 'declaration'
            }
    raise AssertionError(f'no top-level rule for {selector!r} in {CONSOLE_CSS.name}')


def test_the_notice_slot_is_out_of_the_flow():
    """Fixed, so showing a toast does not move the content under the pointer."""
    notices = _declarations('.admin-shell__notices')

    assert notices.get('position') == 'fixed'
    # No margin left over from the in-flow slot: it would reserve nothing, but it says
    # the slot still thinks it is part of the page.
    assert 'margin-block-end' not in notices


def test_a_shown_toast_keeps_the_focused_control_clear():
    """A floating toast must not cover the focused control (WCAG 2.4.11): while one is
    shown, the page keeps the bottom clear when it scrolls focus into view."""
    root = _declarations(':root:has(.admin-shell__notices:not(:empty))')

    assert root.get('scroll-padding-block-end') == 'var(--admin-toast-clearance)'


def test_a_shown_toast_gives_the_page_room_below_its_last_control():
    """Scroll padding does nothing on a page too short to scroll: <main> itself grows by
    the same clearance while a toast shows, so the last control can be scrolled clear."""
    main = _declarations(':root:has(.admin-shell__notices:not(:empty)) .admin-shell__main')

    assert 'var(--admin-toast-clearance)' in main.get('padding-block-end', '')


def test_the_toast_height_is_capped_inside_the_clearance():
    """A long or translated message must not grow the toast past the space the page keeps
    clear: its height is capped, and the excess scrolls inside the toast. The cap applies
    at every width (the phone layout only moves and widens the slot)."""
    toast = _declarations('.admin-shell__notices > *')
    tokens = _declarations(':root')

    assert toast.get('max-block-size') == 'var(--admin-toast-max)'
    assert toast.get('overflow') == 'auto'
    assert toast.get('box-sizing') == 'border-box'
    assert 'var(--admin-toast-max)' in tokens.get('--admin-toast-clearance', '')
    # The toast sits at most 1.5rem above the viewport's bottom edge; the clearance adds
    # more than that to the cap.
    assert '2rem' in tokens['--admin-toast-clearance']
    for at_rule in tinycss2.parse_stylesheet(
        CONSOLE_CSS.read_text(encoding='utf-8'), skip_comments=True, skip_whitespace=True,
    ):
        if at_rule.type == 'at-rule' and at_rule.content:
            for rule in tinycss2.parse_rule_list(at_rule.content, skip_comments=True,
                                                 skip_whitespace=True):
                if rule.type == 'qualified-rule' and 'admin-shell__notices' in tinycss2.serialize(rule.prelude):
                    body = tinycss2.serialize(rule.content)
                    assert 'max-block-size' not in body and 'overflow' not in body, (
                        'the toast cap is not overridden at a narrower width')
