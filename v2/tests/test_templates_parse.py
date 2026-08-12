"""Compile-time syntax gate for every Jinja template (GitHub #300)."""

from pathlib import Path

import pytest
from jinja2 import Environment

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'


@pytest.mark.parametrize('path', sorted(TEMPLATES.glob('*.html')), ids=lambda p: p.name)
def test_jinja_template_parses(path):
    source = path.read_text(encoding='utf-8')
    Environment().parse(source)
