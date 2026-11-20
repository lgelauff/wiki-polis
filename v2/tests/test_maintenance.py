"""Maintenance mode (#619): one flag file pauses participation without stopping the site."""

from pathlib import Path
from unittest.mock import patch

import pytest

import maintenance

_EMPTY_RUN = {'fired': 0, 'aborted': 0, 'skipped': 0, 'failed': 0}
_WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')


def _switch_on(app):
    Path(app.config['MAINTENANCE_FLAG_PATH']).touch()


def _api_writes(app):
    """Every (method, url) under /api/v1 that changes something, built from the URL map.

    Built rather than listed, so a write route added later is covered without editing this.
    """
    adapter = app.url_map.bind('localhost')
    found = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/api/v1/'):
            continue
        values = {name: 1 if type(conv).__name__ == 'IntegerConverter' else 'x'
                  for name, conv in rule._converters.items()}
        if 'side' in values:
            values['side'] = 'pro'
        for method in sorted(set(rule.methods) & set(_WRITE_METHODS)):
            found.append((method, adapter.build(rule.endpoint, values, method=method)))
    return found


def _assert_maintenance_json(response):
    assert response.status_code == 503
    assert response.headers['Retry-After'] == str(maintenance.RETRY_AFTER_SECONDS)
    assert response.get_json()['error']['code'] == 'maintenance'


def _assert_maintenance_page(response):
    assert response.status_code == 503
    assert response.headers['Retry-After'] == str(maintenance.RETRY_AFTER_SECONDS)
    assert response.content_type.startswith('text/html')
    assert '503' in response.get_data(as_text=True)


# ── The switch ────────────────────────────────────────────────────────────────

def test_off_unless_the_flag_file_exists(app):
    assert not maintenance.is_on()
    _switch_on(app)
    assert maintenance.is_on()
    Path(app.config['MAINTENANCE_FLAG_PATH']).unlink()
    assert not maintenance.is_on()


def test_default_flag_lives_in_the_tool_home(monkeypatch, tmp_path):
    monkeypatch.delenv('MAINTENANCE_FLAG_PATH', raising=False)
    monkeypatch.setenv('TOOL_DATA_DIR', str(tmp_path))
    assert maintenance.configured_flag_path() == str(tmp_path / 'maintenance.flag')
    monkeypatch.setenv('MAINTENANCE_FLAG_PATH', '/elsewhere/flag')
    assert maintenance.configured_flag_path() == '/elsewhere/flag'


def test_session_reports_the_switch(app, client):
    assert client.get('/api/v1/session').get_json()['data']['maintenance'] is False
    _switch_on(app)
    response = client.get('/api/v1/session')
    assert response.status_code == 200
    assert response.get_json()['data']['maintenance'] is True


# ── Writes: refused for everyone ──────────────────────────────────────────────

def test_the_write_routes_are_found(app):
    """Guards the builder above: it must see the participant writes the issue names."""
    urls = {url for _method, url in _api_writes(app)}
    for expected in ('/api/v1/conversations/x/statements/1/vote',
                     '/api/v1/conversations/x/statements',
                     '/api/v1/conversations/x/featured-statements/1/arguments',
                     '/api/v1/conversations/x/flags',
                     '/api/v1/conversations/x/participation'):
        assert expected in urls


@pytest.mark.parametrize('who', ['anonymous', 'participant', 'site_admin'])
def test_every_api_write_answers_503_maintenance(app, client, participant, admin_participant,
                                                 who):
    from tests.conftest import login
    if who == 'participant':
        login(client, 'testuser')
    elif who == 'site_admin':
        login(client, 'adminuser')
    _switch_on(app)
    writes = _api_writes(app)
    assert writes
    for method, url in writes:
        response = client.open(url, method=method, json={})
        assert response.status_code == 503, (method, url, response.status_code)
        _assert_maintenance_json(response)


def test_writes_go_through_when_the_switch_is_off(app, auth_client, conversation):
    response = auth_client.put('/api/v1/conversations/test-conv/statements/1/vote',
                               json={'choice': 'sideways'})
    assert response.status_code != 503


def test_the_voucher_form_post_answers_with_the_page(app, client, conversation):
    _switch_on(app)
    _assert_maintenance_page(client.post('/c/test-conv/v', data={'code': 'x'}))


def test_logout_stays_possible(app, auth_client):
    _switch_on(app)
    assert auth_client.post('/logout').status_code != 503


# ── Participation pages and their reads ───────────────────────────────────────

@pytest.mark.parametrize('path', ['/c/test-conv', '/c/test-conv/v', '/c/test-conv/reveal',
                                  '/accept/some-token'])
def test_participation_pages_show_the_maintenance_page(app, auth_client, conversation, path):
    _switch_on(app)
    _assert_maintenance_page(auth_client.get(path))


@pytest.mark.parametrize('read', ['workspace', 'explore', 'arguments', 'informed-voting',
                                  'participation-entry', 'intermediate-results'])
def test_participation_reads_answer_503_for_participants(app, auth_client, conversation, read):
    _switch_on(app)
    _assert_maintenance_json(auth_client.get(f'/api/v1/conversations/test-conv/{read}'))


def test_site_admins_can_still_open_participation_pages(app, admin_client, conversation):
    _switch_on(app)
    assert admin_client.get('/c/test-conv').status_code != 503
    assert admin_client.get('/api/v1/conversations/test-conv/workspace').status_code != 503


@pytest.mark.parametrize('path', [
    '/', '/c/test-conv/about', '/c/test-conv/report', '/help/statements',
    '/api/v1/conversations/test-conv/about', '/api/v1/conversations/test-conv/results',
    '/api/v1/i18n/en',
])
def test_reads_that_need_no_polis_keep_working(app, client, conversation, path):
    _switch_on(app)
    assert client.get(path).status_code != 503


# ── The scheduler ─────────────────────────────────────────────────────────────

def test_scheduler_skips_and_says_so_while_maintenance_is_on(app):
    _switch_on(app)
    with patch('app._process_due_scheduled_transitions', return_value=_EMPTY_RUN) as run:
        result = app.test_cli_runner().invoke(args=['process-phase-schedules'])
    assert result.exit_code == 0, result.output
    run.assert_not_called()
    assert 'maintenance' in result.output


def test_scheduler_runs_when_maintenance_is_off(app):
    with patch('app._process_due_scheduled_transitions', return_value=_EMPTY_RUN) as run:
        result = app.test_cli_runner().invoke(args=['process-phase-schedules'])
    assert result.exit_code == 0, result.output
    run.assert_called_once()
