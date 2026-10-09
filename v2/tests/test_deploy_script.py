"""Static safety checks for the Toolforge deploy entry point."""

import os
import shlex
import subprocess
from pathlib import Path

import pytest


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


def _run_deploy_with_account(tmp_path, account, *, allow_unknown=None):
    home = tmp_path / 'home'
    (home / 'wiki-polis').mkdir(parents=True)
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    log = tmp_path / 'commands.log'

    def executable(name, content):
        path = bin_dir / name
        path.write_text(content, encoding='utf-8')
        path.chmod(0o755)

    executable('whoami', f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(account)}\n")
    executable(
        'git',
        '#!/bin/sh\nprintf "git %s\\n" "$*" >> "$DEPLOY_TEST_LOG"\nexit 91\n',
    )

    env = os.environ.copy()
    env.update({
        'HOME': str(home),
        'PATH': f"{bin_dir}:{env.get('PATH', '')}",
        'DEPLOY_TEST_LOG': str(log),
    })
    env.pop('ALLOW_UNKNOWN_TOOL', None)
    if allow_unknown is not None:
        env['ALLOW_UNKNOWN_TOOL'] = allow_unknown

    result = subprocess.run(
        ['bash', str(DEPLOY_SCRIPT), 'main'],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    return result, log


def test_deploy_rejects_an_unknown_tool_account_before_git_fetch(tmp_path):
    result, log = _run_deploy_with_account(tmp_path, 'tools.unexpected')

    assert result.returncode == 1
    assert (
        "deploy.sh: active account is 'tools.unexpected', not a known wiki-polis tool. "
        "You are probably in the wrong 'become' context. Aborting."
    ) in result.stderr
    assert not log.exists()


@pytest.mark.parametrize('account', ['tools.wiki-polis', 'tools.wiki-polis-dev'])
def test_deploy_allows_the_two_known_tool_accounts(tmp_path, account):
    result, log = _run_deploy_with_account(tmp_path, account)

    assert result.returncode == 91
    assert log.read_text(encoding='utf-8') == 'git fetch --prune origin\n'


def test_deploy_requires_exact_override_for_an_unknown_tool_account(tmp_path):
    result, log = _run_deploy_with_account(
        tmp_path, 'tools.new-environment', allow_unknown='true',
    )

    assert result.returncode == 1
    assert 'tools.new-environment' in result.stderr
    assert not log.exists()


def test_deploy_allows_an_unknown_tool_account_with_explicit_override(tmp_path):
    result, log = _run_deploy_with_account(
        tmp_path, 'tools.new-environment', allow_unknown='1',
    )

    assert result.returncode == 91
    assert 'ALLOW_UNKNOWN_TOOL=1' in result.stderr
    assert log.read_text(encoding='utf-8') == 'git fetch --prune origin\n'
