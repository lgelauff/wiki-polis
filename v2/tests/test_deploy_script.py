"""Static safety checks for the Toolforge deploy entry point."""

import subprocess
from pathlib import Path


DEPLOY_SCRIPT = Path(__file__).resolve().parents[2] / 'deploy.sh'


def test_deploy_script_is_valid_bash_and_documents_revision_pinning():
    subprocess.run(['bash', '-n', str(DEPLOY_SCRIPT)], check=True)
    help_result = subprocess.run(
        ['bash', str(DEPLOY_SCRIPT), '--help'],
        check=True,
        capture_output=True,
        text=True,
    )

    assert '--pr NUMBER' in help_result.stdout
    assert '--expect SHA' in help_result.stdout


def test_deploy_script_prunes_refs_and_has_no_obsolete_component_warning():
    source = DEPLOY_SCRIPT.read_text(encoding='utf-8')

    assert 'git fetch --prune origin' in source
    assert 'refs/pull/$PULL_REQUEST/head' in source
    assert 'particiapp-web-components.js' not in source
