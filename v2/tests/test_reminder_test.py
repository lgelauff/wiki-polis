"""Test sends from the Proto bot (#577): the guards, dry runs, the Meta fallback, the API,
the audit row and the CLI."""

from unittest.mock import patch

import pytest

from db import AuditEvent
from services.reminder_test import (
    DRY_RUN, FAILED, FALLBACK_NOT_LIVE, NO_CREDENTIALS, SENT, UNKNOWN, WIKI_NOT_LIVE,
    ReminderSettings, ReminderTestMessage, ReminderTestRefused, normalize_username,
    send_test_message,
)
from services.wiki_bot import (
    NOBOTS, NOT_EMAILABLE, OUTCOME_UNKNOWN, THROTTLED, BotCredentials, WikiBotError,
)

MESSAGE = ReminderTestMessage(subject='Proto test message', body='Body', summary='Summary')


class FakeBot:
    """Stands in for WikiBotClient on one wiki; every instance shares one log."""

    def __init__(self, wiki, log, *, login=None, emailable=(), talk_blocked=False, error=None):
        self.wiki = wiki
        self.login = login
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
        self._log.append(('login', self.login.username))

    def post_talk_section(self, username, *, title, text, summary):
        if self._error:
            raise self._error
        self._log.append(('talk', self.wiki, username, title, text, summary))
        self._log.append(('login', self.login.username))
        return 1


def settings(*, live=('nlwiki', 'metawiki'), recipients=('Tester',), credentials=True):
    return ReminderSettings(
        email_credentials=BotCredentials('Protowikibot@mail', 'pw') if credentials else None,
        talk_credentials=BotCredentials('Protowikibot@talk', 'pw') if credentials else None,
        live_wikis=frozenset(live), test_recipients=tuple(recipients), user_agent='x',
    )


def run(wiki='nlwiki', channel='email', recipient='Tester', *, conf=None, log=None, **bot):
    log = [] if log is None else log
    result = send_test_message(
        wiki=wiki, channel=channel, recipient=recipient, settings=conf or settings(),
        message=MESSAGE, client_factory=lambda w, c: FakeBot(w, log, login=c, **bot),
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
    assert log[-2] == ('email', 'nlwiki', 'Tester', 'Proto test message', 'Body')
    assert log[-1] == ('login', 'Protowikibot@mail')


def test_email_falls_back_to_meta():
    result, log = run(emailable=('metawiki',))
    assert (result.outcome, result.sent_via) == (SENT, 'metawiki')
    assert log[-2][:2] == ('email', 'metawiki')


def test_no_fallback_when_meta_is_not_live_and_the_result_says_so():
    result, log = run(conf=settings(live=('nlwiki',)), emailable=('metawiki',))
    assert (result.outcome, result.reason, result.code) == (FAILED, NOT_EMAILABLE, FALLBACK_NOT_LIVE)
    assert not [entry for entry in log if entry[0] == 'email']
    assert not [entry for entry in log if entry[1] == 'metawiki']   # Meta was not even asked


def test_not_emailable_after_trying_meta_has_no_fallback_code():
    result, log = run(emailable=())
    assert (result.reason, result.code) == (NOT_EMAILABLE, None)
    assert ('emailable?', 'metawiki', 'Tester') in log


def test_a_send_without_an_answer_has_an_unknown_outcome():
    result, _ = run(emailable=('nlwiki',), error=WikiBotError(OUTCOME_UNKNOWN, 'timeout'))
    assert (result.outcome, result.reason) == (UNKNOWN, OUTCOME_UNKNOWN)


def test_settings_accept_a_comma_separated_string():
    conf = ReminderSettings.from_config({
        'REMINDERS_LIVE_WIKIS': 'nlwiki, enwiki', 'REMINDERS_TEST_RECIPIENTS': 'tester, Tester two,',
    }, user_agent='x')
    assert conf.live_wikis == frozenset({'nlwiki'})
    assert conf.test_recipients == ('Tester', 'Tester two')
    assert conf.email_credentials is None and conf.talk_credentials is None


def test_not_emailable_anywhere_fails_and_never_moves_to_the_talk_page():
    result, log = run(emailable=())
    assert (result.outcome, result.reason) == (FAILED, NOT_EMAILABLE)
    assert not [entry for entry in log if entry[0] in ('email', 'talk')]


def test_talk_page_note_is_signed():
    result, log = run(channel='talk')
    assert (result.outcome, result.sent_via) == (SENT, 'nlwiki')
    assert log[-2] == ('talk', 'nlwiki', 'Tester', 'Proto test message', 'Body ~~~~', 'Summary')
    assert log[-1] == ('login', 'Protowikibot@talk')


def test_each_channel_needs_its_own_login():
    conf = ReminderSettings(
        email_credentials=BotCredentials('Protowikibot@mail', 'pw'), talk_credentials=None,
        live_wikis=frozenset({'nlwiki'}), test_recipients=('Tester',), user_agent='x',
    )
    talk, log = run(channel='talk', conf=conf)
    assert (talk.outcome, talk.reason) == (DRY_RUN, NO_CREDENTIALS) and log == []
    email, _ = run(conf=conf, emailable=('nlwiki',))
    assert email.outcome == SENT


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
        REMINDERS_BOT_EMAIL_USERNAME='Protowikibot@mail', REMINDERS_BOT_EMAIL_PASSWORD='pw',
        REMINDERS_LIVE_WIKIS=['nlwiki'], REMINDERS_TEST_RECIPIENTS=['Tester'],
    )
    log = []
    with patch('services.reminder_test.WikiBotClient',
               side_effect=lambda wiki, **kw: FakeBot(
                   wiki, log, login=kw['credentials'], emailable=('nlwiki',))):
        yield log


def test_state_is_for_site_admins_only(auth_client, configured):
    assert auth_client.get('/api/v1/admin/reminder-test').status_code == 403
    assert auth_client.post('/api/v1/admin/reminder-test-sends', json={
        'wiki': 'nlwiki', 'channel': 'email', 'recipient': 'Tester',
    }).status_code == 403
    assert configured == []


def test_state_lists_wikis_test_accounts_and_login(admin_client, configured):
    data = admin_client.get('/api/v1/admin/reminder-test').get_json()['data']
    assert data['recipients'] == ['Tester']
    assert data['credentialsSet'] == {'email': True, 'talk': False}
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
    assert configured[-2][:3] == ('email', 'nlwiki', 'Tester')
    assert configured[-1] == ('login', 'Protowikibot@mail')
    event = AuditEvent.query.filter_by(operation='reminder.test').one()
    assert event.outcome == 'sent' and event.detail['wiki'] == 'nlwiki'
    assert 'Tester' not in repr(event.detail) and event.target_id is None


def test_send_to_an_account_that_is_not_listed_is_refused_and_audited(admin_client, configured):
    response = admin_client.post('/api/v1/admin/reminder-test-sends', json={
        'wiki': 'nlwiki', 'channel': 'email', 'recipient': 'SomeoneElse',
    })
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'recipient_not_allowed'
    assert configured == []
    event = AuditEvent.query.filter_by(operation='reminder.test').one()
    assert event.outcome == 'refused' and event.detail['reason'] == 'recipient_not_allowed'
    assert 'SomeoneElse' not in repr(event.detail)


def test_refused_request_audits_only_known_values(admin_client, configured):
    admin_client.post('/api/v1/admin/reminder-test-sends', json={
        'wiki': 'evil.example', 'channel': 'email', 'recipient': 'Tester',
    })
    event = AuditEvent.query.filter_by(operation='reminder.test').one()
    assert event.detail['wiki'] == 'other' and event.detail['reason'] == 'unknown_wiki'


def test_send_rejects_a_malformed_body(admin_client, configured):
    response = admin_client.post('/api/v1/admin/reminder-test-sends', json={'wiki': 'nlwiki'})
    assert response.status_code == 400


def test_cli_sends_and_reports(app, configured):
    result = app.test_cli_runner().invoke(args=[
        'send-test-reminder', '--wiki', 'nlwiki', '--channel', 'email', '--to', 'Tester',
    ])
    assert result.exit_code == 0, result.output
    assert 'sent (sent from nlwiki)' in result.output
    event = AuditEvent.query.filter_by(operation='reminder.test').one()
    assert event.detail['actor_kind'] == 'cli'


def test_cli_dry_run_on_a_wiki_that_is_not_live(app, configured):
    result = app.test_cli_runner().invoke(args=[
        'send-test-reminder', '--wiki', 'metawiki', '--channel', 'talk', '--to', 'Tester',
    ])
    assert result.exit_code == 0, result.output
    assert 'dry_run, reason wiki_not_live' in result.output
    assert configured == []


def test_cli_names_the_settings_to_fill_when_a_login_is_missing(app, configured):
    result = app.test_cli_runner().invoke(args=[
        'send-test-reminder', '--wiki', 'nlwiki', '--channel', 'talk', '--to', 'Tester',
    ])
    assert 'set REMINDERS_BOT_TALK_USERNAME and REMINDERS_BOT_TALK_PASSWORD' in result.output


def test_cli_names_the_empty_half_of_a_login(app, configured):
    app.config['REMINDERS_BOT_TALK_USERNAME'] = 'Protowikibot@talk'
    result = app.test_cli_runner().invoke(args=[
        'send-test-reminder', '--wiki', 'nlwiki', '--channel', 'talk', '--to', 'Tester',
    ])
    assert 'REMINDERS_BOT_TALK_PASSWORD is empty' in result.output


def test_login_settings_come_from_the_toolforge_secret_names(monkeypatch):
    import app as app_module
    from services.reminder_test import login_settings
    decoys = {
        'REMINDERS_BOT_EMAIL_USERNAME': 'Decoy@mail', 'REMINDERS_BOT_EMAIL_PASSWORD': 'decoy-1',
        'REMINDERS_BOT_TALK_USERNAME': 'Decoy@talk', 'REMINDERS_BOT_TALK_PASSWORD': 'decoy-2',
    }
    for name, value in decoys.items():
        monkeypatch.setenv(name, value)
    settings_ = login_settings(app_module._read_secret)
    assert settings_ == decoys
    conf = ReminderSettings.from_config(settings_, user_agent='x')
    assert conf.credentials_for('email') == BotCredentials('Decoy@mail', 'decoy-1')
    assert conf.credentials_for('talk') == BotCredentials('Decoy@talk', 'decoy-2')


def test_secret_names_are_the_ones_set_on_toolforge():
    from services.reminder_test import login_settings
    asked = []
    login_settings(lambda name: asked.append(name) or '')
    assert sorted(asked) == [
        'reminders-bot-email-password', 'reminders-bot-email-username',
        'reminders-bot-talk-password', 'reminders-bot-talk-username',
    ]


def test_an_unknown_channel_has_no_login():
    with pytest.raises(KeyError):
        settings().credentials_for('sms')


def test_a_half_set_login_is_named():
    from services.reminder_test import missing_login_parts
    assert missing_login_parts({'REMINDERS_BOT_EMAIL_USERNAME': 'a@b'}) == {
        'email': ['REMINDERS_BOT_EMAIL_PASSWORD'],
    }
    assert missing_login_parts({}) == {}


def test_cli_refuses_an_account_that_is_not_listed(app, configured):
    result = app.test_cli_runner().invoke(args=[
        'send-test-reminder', '--wiki', 'nlwiki', '--channel', 'email', '--to', 'Other',
    ])
    assert result.exit_code == 2 and 'recipient_not_allowed' in result.output
