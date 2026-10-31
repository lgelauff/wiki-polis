"""Reminder texts and the real sender, against a fake wiki (#577). No network."""

import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.reminder_batch import Outcome
from services.reminder_messages import MessageSettings, build_email, build_talk
from services.reminder_sender import LiveSender
from services.reminders import PHASE_CLOSING, PHASE_OPENED, RESULTS
from services.wiki_bot import (
    API_ERROR, BLOCKED, LAGGED, NOT_EMAILABLE, OUTCOME_UNKNOWN, WikiBotClient, WikiBotError,
)
from tests.test_wiki_bot import FakeSession

SETTINGS = MessageSettings(base_url='https://proto.example/', operator='Some Operator')
EN = json.loads((Path(__file__).parents[1] / 'i18n' / 'en.json').read_text(encoding='utf-8'))


def _conv(title='Library hours', slug='library-hours', named=False, language='en'):
    return SimpleNamespace(title=title, slug=slug, language=language,
                           reminder_talk_names_consultation=named)


def _rem(kind=PHASE_OPENED, phase='submission', **conv):
    return SimpleNamespace(reminder_type=kind, phase_key='' if kind == RESULTS else phase,
                           send_day=date(2026, 11, 2), conversation=_conv(**conv))


# ── Texts ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('kind', [PHASE_OPENED, PHASE_CLOSING, RESULTS])
def test_every_type_has_a_mail_and_a_talk_text_with_no_missing_message(app, kind):
    for named in (True, False):
        for message in (build_email([_rem(kind, named=named)], SETTINGS),
                        build_talk([_rem(kind, named=named)], SETTINGS)):
            text = message.subject + message.body + message.summary
            assert '⧼' not in text and '$' not in text


def test_a_mail_names_the_consultation_links_to_it_and_ends_with_the_footer(app):
    message = build_email([_rem()], SETTINGS)
    assert 'Library hours' in message.subject
    assert 'https://proto.example/c/library-hours' in message.body
    assert 'Explore' in message.body                       # the phase name, reused
    assert 'asked for reminders' in message.body
    assert 'User:Some_Operator' in message.body             # the operator's user page
    assert 'User_talk:Protowikibot' in message.body          # where questions go
    assert 'not read' in message.body


def test_one_mail_combines_several_consultations(app):
    message = build_email([_rem(), _rem(RESULTS, title='Park plan', slug='park')], SETTINGS)
    assert message.subject.startswith('2 updates')
    assert 'Library hours' in message.body and 'Park plan' in message.body
    assert 'these consultations' in message.body


def test_a_talk_note_does_not_name_the_consultation_unless_its_setting_is_on(app):
    unnamed = build_talk([_rem(named=False)], SETTINGS)
    assert 'Library hours' not in unnamed.subject + unnamed.body
    assert '/c/library-hours' not in unnamed.body
    assert 'https://proto.example' in unnamed.body           # Proto's front page instead
    named = build_talk([_rem(named=True)], SETTINGS)
    assert 'Library hours' in named.body and '/c/library-hours' in named.body


def test_a_mixed_talk_note_names_only_the_consultations_that_allow_it(app):
    message = build_talk([_rem(named=True), _rem(title='Secret', slug='secret', named=False)],
                         SETTINGS)
    assert 'Library hours' in message.body
    assert 'Secret' not in message.body and '/c/secret' not in message.body


def test_no_text_carries_a_vote_count_or_an_exact_number_of_open_items():
    reminder_keys = [k for k in EN if k.startswith('reminder-')]
    assert len(reminder_keys) == 16
    for key in reminder_keys:
        assert not re.search(r'\bvote', EN[key], re.I), key


def test_an_unknown_type_is_refused(app):
    with pytest.raises(ValueError):
        build_email([_rem('unanswered')], SETTINGS)


# ── The real sender, against fakes ───────────────────────────────────────────

class FakeClient:
    def __init__(self, wiki, *, emailable=True, allows=True, opted_out=False, fail=None):
        self.wiki = wiki
        self.emailable, self.allows, self.opted_out, self.fail = emailable, allows, opted_out, fail
        self.sent, self.posts, self.closed = [], [], False

    def is_emailable(self, username):
        return self.emailable

    def talk_page_allows_bot(self, username):
        return self.allows

    def talk_page_opted_out(self, username):
        return self.opted_out

    def send_email(self, username, *, subject, text):
        if self.fail:
            raise self.fail
        self.sent.append((username, subject))

    def post_talk_section(self, username, *, title, text, summary):
        if self.fail:
            raise self.fail
        self.posts.append((username, title, text))
        return 1

    def close(self):
        self.closed = True


def _sender(clients, **kw):
    made = []

    def client_for(wiki, channel):
        made.append((wiki, channel))
        return clients[(wiki, channel)]
    sender = LiveSender(client_for=client_for, messages=SETTINGS, **kw)
    return sender, made


PERSON = SimpleNamespace(participant=SimpleNamespace(mw_username='Tester'))


def _send(sender, channel, wiki='nlwiki'):
    return sender.send(channel=channel, wiki=wiki, participation=PERSON, reminders=[_rem()])


def test_mail_goes_from_the_consultations_wiki_when_it_can(app):
    nl = FakeClient('nlwiki')
    sender, _ = _sender({('nlwiki', 'email'): nl})
    assert _send(sender, 'email') == Outcome('sent', sent_via='nlwiki')
    assert nl.sent[0][0] == 'Tester'


def test_mail_falls_back_to_meta(app):
    nl, meta = FakeClient('nlwiki', emailable=False), FakeClient('metawiki')
    sender, _ = _sender({('nlwiki', 'email'): nl, ('metawiki', 'email'): meta})
    assert _send(sender, 'email') == Outcome('sent', sent_via='metawiki')
    assert nl.sent == [] and len(meta.sent) == 1


def test_mail_that_neither_wiki_can_deliver_is_not_emailable(app):
    sender, _ = _sender({('nlwiki', 'email'): FakeClient('nlwiki', emailable=False),
                         ('metawiki', 'email'): FakeClient('metawiki', emailable=False)})
    assert _send(sender, 'email') == Outcome('failed', reason=NOT_EMAILABLE)


def test_a_refusal_after_a_passing_check_is_refused_and_not_retried_from_meta(app):
    nl = FakeClient('nlwiki', fail=WikiBotError(NOT_EMAILABLE, 'nowikiemail'))
    meta = FakeClient('metawiki')
    sender, made = _sender({('nlwiki', 'email'): nl, ('metawiki', 'email'): meta})
    assert _send(sender, 'email') == Outcome('failed', reason='refused', error_code='nowikiemail')
    assert ('metawiki', 'email') not in made


@pytest.mark.parametrize('error', [
    WikiBotError(BLOCKED, 'blocked'), WikiBotError(LAGGED, 'maxlag'),
    WikiBotError(OUTCOME_UNKNOWN, 'timeout'), WikiBotError(API_ERROR, 'readonly'),
])
@pytest.mark.parametrize('channel', ['email', 'talk'])
def test_other_failures_keep_the_clients_reason_and_code(app, error, channel):
    sender, _ = _sender({('nlwiki', channel): FakeClient('nlwiki', fail=error)})
    assert _send(sender, channel) == Outcome('failed', reason=error.reason, error_code=error.code)


@pytest.mark.parametrize('fields', [{'allows': False}, {'opted_out': True}])
def test_a_talk_page_that_keeps_bots_out_or_opted_out_gets_no_post(app, fields):
    talk = FakeClient('nlwiki', **fields)
    sender, _ = _sender({('nlwiki', 'talk'): talk})
    assert _send(sender, 'talk') == Outcome('failed', reason='nobots')
    assert talk.posts == []


def test_a_talk_post_is_signed_and_titled(app):
    talk = FakeClient('nlwiki')
    sender, _ = _sender({('nlwiki', 'talk'): talk})
    assert _send(sender, 'talk') == Outcome('sent', sent_via='nlwiki')
    username, title, text = talk.posts[0]
    assert username == 'Tester' and title.startswith('Proto:') and text.endswith('~~~~')


@pytest.mark.parametrize('approved, gap', [(None, 10.0), ({'nlwiki': '#581'}, 2.0)])
def test_talk_posts_on_one_wiki_are_spaced_by_its_interval(app, approved, gap):
    now = [100.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds
    talk = FakeClient('nlwiki')
    sender, _ = _sender({('nlwiki', 'talk'): talk}, approved=approved, sleep=sleep,
                        clock=lambda: now[0])
    _send(sender, 'talk')
    now[0] += 1.0
    _send(sender, 'talk')
    assert slept == [pytest.approx(gap - 1.0)] and len(talk.posts) == 2


def test_the_sender_closes_its_clients(app):
    talk = FakeClient('nlwiki')
    sender, _ = _sender({('nlwiki', 'talk'): talk})
    _send(sender, 'talk')
    sender.close()
    assert talk.closed


def test_the_command_still_uses_the_dry_run_sender():
    source = (Path(__file__).parents[1] / 'app.py').read_text(encoding='utf-8')
    assert 'LiveSender' not in source and 'sender=DryRunSender()' in source


# ── The client's opt-out category check ──────────────────────────────────────

def _client(answer):
    session = FakeSession(answer)
    return WikiBotClient('nlwiki', credentials=None, user_agent='t',
                         session_factory=lambda: session), session


def test_the_opt_out_category_is_the_wikis_own_and_read_once():
    def answer(method, params):
        if params.get('meta') == 'allmessages':
            return {'query': {'allmessages': [{'content': 'Geen berichten'}]}}
        assert params['clcategories'] == 'Category:Geen berichten'
        return {'query': {'pages': [{'categories': [{'title': 'Categorie:Geen berichten'}]}]}}
    client, session = _client(answer)
    assert client.talk_page_opted_out('Tester') is True
    assert client.talk_page_opted_out('Other') is True
    assert sum(1 for c in session.calls if c[2].get('meta') == 'allmessages') == 1


def test_the_default_category_is_used_when_the_wiki_has_none():
    def answer(method, params):
        if params.get('meta') == 'allmessages':
            return {'query': {'allmessages': [{'missing': True}]}}
        assert params['clcategories'] == 'Category:Opted-out of message delivery'
        return {'query': {'pages': [{}]}}
    client, _ = _client(answer)
    assert client.talk_page_opted_out('Tester') is False
