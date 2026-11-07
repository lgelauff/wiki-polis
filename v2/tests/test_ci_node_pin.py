"""CI must pin Node to an exact, patched release, never a floating major or alias."""

import re
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[2] / '.github' / 'workflows'

# Lowest patched release per major line (Node security release of 2026-10-20).
# Raise these when a later security release lands; a major not listed here fails.
PATCHED_MINIMUM = {22: (22, 23, 4), 24: (24, 22, 1), 26: (26, 12, 1)}


def _setup_node_steps():
    """Yield (workflow name, node-version or None) for every actions/setup-node step."""
    for workflow in sorted(WORKFLOWS.glob('*.y*ml')):
        lines = workflow.read_text(encoding='utf-8').splitlines()
        for i, line in enumerate(lines):
            if not re.search(r'uses:\s*actions/setup-node@', line):
                continue
            indent = len(line) - len(line.lstrip(' -'))
            version = None
            for follow in lines[i + 1:]:
                stripped = follow.lstrip(' ')
                if stripped and len(follow) - len(follow.lstrip(' -')) < indent:
                    break
                if stripped.startswith('- '):
                    break
                match = re.match(r'\s*node-version:\s*(.+?)\s*$', follow)
                if match:
                    version = match.group(1).strip('"\'')
                    break
            yield workflow.name, version


def test_every_setup_node_step_pins_an_exact_patched_release():
    steps = list(_setup_node_steps())
    assert steps, 'no actions/setup-node step in any workflow'
    for name, version in steps:
        assert version is not None, f'{name}: setup-node step without node-version'
        assert re.fullmatch(r'\d+\.\d+\.\d+', version), f'{name}: node-version {version!r} is not exact'
        parts = tuple(int(p) for p in version.split('.'))
        assert parts[0] in PATCHED_MINIMUM, f'{name}: Node {parts[0]} is not a patched major line'
        assert parts >= PATCHED_MINIMUM[parts[0]], f'{name}: Node {version} is below the patched release'
