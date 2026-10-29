"""Test sends from the Proto bot (#577): the guards, dry runs, the Meta fallback, the API,
the audit row and the CLI."""

from unittest.mock import patch

import pytest

from db import AuditEvent
from services.reminder_test import (
    DRY_RUN, FAILED, NO_CREDENTIALS, SENT, WIKI_NOT_LIVE, ReminderSettings, ReminderTestMessage,
    ReminderTestRefused, normalize_username, send_test_message,
)
from services.wiki_bot import NOBOTS, NOT_EMAILABLE, THROTTLED, BotCredentials, WikiBotError

MESSAGE = ReminderTestMessage(subject='Proto test message', body='Body', summary='Summary')


class FakeBot:
    """Stands in for WikiBotClient on one wiki; every instance shares one log."""

    def __init__(self, wiki, log, *, emailable=(), talk_blocked=False, error=None):
        self.wiki = wiki
        self._log = log
        self._emailable = emailable
        self._talk_blocked = talk_blocked
        self._error = error

    def is_emailable(self, username):
        self._log.append(('emailable?', self.wiki, username))
        return self.wiki in self._emailable

    def talk_page_allows_bot(self, username):
        return not self._talk_blocked

    def send_email(self, username, *, subject, text):
        if self._error:
            raise self._error
        self._log.append(('email', self.wiki, username, subject, text))

    def post_talk_section(self, username, *, title, text, summary):
        if self._error:
            raise self._error
        self._log.append(('talk', self.wiki, username, title, text, summary))
        return 1


def settings(*, live=('nlwiki', 'metawiki'), recipients=('Tester',), credentials=True):
    return ReminderSettings(
        credentials=BotCredentials('ProtoWikiBot@r', 'pw') if credentials else None,
        live_wikis=frozenset(live), test_recipients=tuple(recipients), user_agent='x',
    )


def run(wiki='nlwiki', channel='email', recipient='Tester', *, conf=None, log=None, **bot):
    log = [] if log is None else log
    result = send_test_message(
        wiki=wiki, channel=channel, recipient=recipient, settings=conf or settings(),
        message=MESSAGE, client_factory=lambda w: FakeBot(w, log, **bot),
    )
    return result, log


def test_username_is_normalized_like_mediawiki():
    assert normalize_username('  tester_one ') == 'Tester one'


@pytest.mark.parametrize('wiki, channel, recipient, code', [
    ('enwiki', 'email', 'Tester', 'unknown_wiki'),
    ('nlwiki', 'sms', 'Tester', 'unknown_channel'),
    ('nlwiki', 'email', 'SomeoneElse', 'recipient_not_allowed'),
])
def test_requests_outside_the_configuration_are_refused_before_anything_happens(
        wiki, channel, recipient, code):
    log = []
    with pytest.raises(ReminderTestRefused) as raised:
        run(wiki, channel, recipient, log=log, emailable=('nlwiki',))
    assert raised.value.code == code
    assert log == []


def test_a_wiki_that_is_not_live_is_a_dry_run():
    result, log = run(conf=settings(live=()), emailable=('nlwiki',))
    assert (result.outcome, result.reason) == (DRY_RUN, WIKI_NOT_LIVE)
    assert log == []


def test_no_bot_login_is_a_dry_run():
    result, log = run(conf=settings(credentials=False), emailable=('nlwiki',))
    assert (result.outcome, result.reason) == (DRY_RUN, NO_CREDENTIALS)
    assert log == []


def test_email_is_sent_from_the_chosen_wiki_when_the_account_accepts_it_there():
    result, log = run(recipient='tester', emailable=('nlwiki', 'metawiki'))
    assert (result.outcome, result.sent_via) == (SENT, 'nlwiki')
    assert log[-1] == ('email', 'nlwiki', 'Tester', 'Proto test message', 'Body')


def test_email_falls_back_to_meta():
    result, log = run(emailable=('metawiki',))
    assert (result.outcome, result.sent_via) == (SENT, 'metawiki')
    assert log[-1][:2] == ('email', 'metawiki')


def test_no_fallback_when_meta_is_not_live():
    result, log = run(conf=settings(live=('nlwiki',)), emailable=('metawiki',))
    assert (result.outcome, result.reason) == (FAILED, NOT_EMAILABLE)
    assert not [entry for entry in log if entry[0] == 'email']


def test_not_emailable_anywhere_fails_and_never_moves_to_the_talk_page():
    result, log = run(emailable=())
    assert (result.outcome, result.reason) == (FAILED, NOT_EMAILABLE)
    assert not [entry for entry in log if entry[0] in ('email', 'talk')]


def test_talk_page_note_is_signed():
    result, log = run(channel='talk')
    assert (result.outcome, result.sent_via) == (SENT, 'nlwiki')
    assert log[-1] == ('talk', 'nlwiki', 'Tester', 'Proto test message', 'Body ~~~~', 'Summary')


def test_nobots_stops_the_talk_page_note():
    result, log = run(channel='talk', talk_blocked=True)
    assert (result.outcome, result.reason) == (FAILED, NOBOTS)
    assert log == []


def test_a_wiki_error_is_reported_with_its_reason_and_code():
    result, _ = run(emailable=('nlwiki',), error=WikiBotError(THROTTLED, 'ratelimited'))
    assert (result.outcome, result.reason, result.code) == (FAILED, THROTTLED, 'ratelimited')


# -- API, audit and CLI ---------------------------------------------------------------

@pytest.fixture
def configured(app):
    app.config.update(
        REMINDERS_BOT_USERNAME='ProtoWikiBot@r', REMINDERS_BOT_PASSWORD='pw',
        REMINDERS_LIVE_WIKIS=['nlwiki'], REMINDERS_TEST_RECIPIENTS=['Tester'],
    )
    log = []
    with patch('services.reminder_test.WikiBotClient',
               side_effect=lambda wiki, **_: FakeBot(wiki, log, emailable=('nlwiki',))):
        yield log


def test_state_is_for_site_admins_only(auth_client, configured):
    assert auth_client.get('/api/v1/admin/reminder-test').status_code == 403
    assert auth_client.post('/api/v1/admin/reminder-test-sends', json={
        'wiki': 'nlwiki', 'channel': 'email', 'recipient': 'Tester',
    }).status_code == 403
    assert configured == []


def test_state_lists_wikis_test_accounts_and_login(admin_client, configured):
    data = admin_client.get('/api/v1/admin/reminder-test').get_json()['data']
    assert data['recipients'] == ['Tester'] and data['credentialsSet'] is True
    assert {(row['key'], row['live']) for row in data['wikis']} == {
        ('nlwiki', True), ('metawiki', False),
    }


def test_send_returns_the_result_and_audits_without_the_name(admin_client, configured):
    response = admin_client.post('/api/v1/admin/reminder-test-sends', json={
        'wiki': 'nlwiki', 'channel': 'email', 'recipient': 'Tester',
    })
    assert response.status_code == 200
    assert response.get_json()['data'] == {
        'outcome': 'sent', 'reason': None, 'code': None, 'sentVia': 'nlwiki',
    }
    assert configured[-1][:3] == ('email', 'nlwiki', 'Tester')
    event = AuditEvent.query.filter_by(operation='reminder.test').one()
    assert event.outcome == 'sent' and event.detail['wiki'] == 'nlwiki'
    assert 'Tester' not in repr(event.detail) and event.target_id is None


def test_send_to_an_account_that_is_not_listed_is_refused(admin_client, configured):
    response = admin_client.post('/api/v1/admin/reminder-test-sends', json={
        'wiki': 'nlwiki', 'channel': 'email', 'recipient': 'SomeoneElse',
    })
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'recipient_not_allowed'
    assert configured == []


def test_send_rejects_a_malformed_body(admin_client, configured):
    response = admin_client.post('/api/v1/admin/reminder-test-sends', json={'wiki': 'nlwiki'})
    assert response.status_code == 400


def test_cli_sends_and_reports(app, configured):
    result = app.test_cli_runner().invoke(args=[
        'send-test-reminder', '--wiki', 'nlwiki', '--channel', 'email', '--to', 'Tester',
    ])
    assert result.exit_code == 0, result.output
    assert 'sent (sent from nlwiki)' in result.output


def test_cli_dry_run_on_a_wiki_that_is_not_live(app, configured):
    result = app.test_cli_runner().invoke(args=[
        'send-test-reminder', '--wiki', 'metawiki', '--channel', 'talk', '--to', 'Tester',
    ])
    assert result.exit_code == 0, result.output
    assert 'dry_run, reason wiki_not_live' in result.output
    assert configured == []


def test_cli_refuses_an_account_that_is_not_listed(app, configured):
    result = app.test_cli_runner().invoke(args=[
        'send-test-reminder', '--wiki', 'nlwiki', '--channel', 'email', '--to', 'Other',
    ])
    assert result.exit_code == 2 and 'recipient_not_allowed' in result.output
