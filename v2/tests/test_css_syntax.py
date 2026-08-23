"""Parse all application CSS and fail on syntax errors (GitHub #300)."""

from pathlib import Path

import pytest
import tinycss2

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'static'
STYLESHEETS = [*sorted(STATIC.glob('*.css')), ROOT / 'frontend' / 'src' / 'styles.css']
_RULE_LIST_AT_RULES = {'container', 'keyframes', '-webkit-keyframes', 'layer', 'media', 'supports'}


def _errors(nodes):
    for node in nodes:
        if node.type == 'error':
            yield node
        elif node.type == 'qualified-rule':
            yield from _errors(tinycss2.parse_declaration_list(node.content))
        elif node.type == 'at-rule' and node.content is not None:
            parser = (tinycss2.parse_rule_list
                      if node.lower_at_keyword in _RULE_LIST_AT_RULES
                      else tinycss2.parse_declaration_list)
            yield from _errors(parser(node.content))


@pytest.mark.parametrize('path', STYLESHEETS, ids=lambda p: p.name)
def test_css_parses_without_errors(path):
    stylesheet = tinycss2.parse_stylesheet(
        path.read_text(encoding='utf-8'),
        skip_comments=True,
        skip_whitespace=True,
    )
    errors = list(_errors(stylesheet))
    assert not errors, '\n'.join(
        f'{path.name}:{error.source_line}:{error.source_column}: {error.message}'
        for error in errors
    )
