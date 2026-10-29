"""The Proto bot's MediaWiki client (#577): exclusion templates, login, sends, error mapping."""

import pytest
import requests

from services.wiki_bot import (
    API_ERROR, BLOCKED, NOT_EMAILABLE, THROTTLED, BotCredentials, WikiBotClient, WikiBotError,
    bot_allowed,
)


@pytest.mark.parametrize('text, allowed', [
    ('', True),
    ('Hello, see you.', True),
    ('{{nobots}}', False),
    ('{{ NoBots }}', False),
    ('{{bots}}', True),
    ('{{bots|deny=all}}', False),
    ('{{bots|deny=SomeOtherBot, ProtoWikiBot}}', False),
    ('{{bots|deny=SomeOtherBot}}', True),
    ('{{bots|allow=none}}', False),
    ('{{bots|allow=all}}', True),
    ('{{bots|allow=ProtoWikiBot}}', True),
    ('{{bots|allow=SomeOtherBot}}', False),
])
def test_bot_exclusion_templates(text, allowed):
    assert bot_allowed(text, 'ProtoWikiBot') is allowed


def test_bot_password_suffix_is_ignored_when_matching_names():
    assert bot_allowed('{{bots|deny=ProtoWikiBot}}', 'ProtoWikiBot@reminders') is False


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


class FakeSession:
    """Answers MediaWiki API calls from a script; records every call."""

    def __init__(self, answer):
        self.headers = {}
        self.calls = []
        self._answer = answer

    def get(self, url, params, timeout):
        self.calls.append(('GET', url, dict(params)))
        return FakeResponse(self._answer('GET', params))

    def post(self, url, data, timeout):
        self.calls.append(('POST', url, dict(data)))
        return FakeResponse(self._answer('POST', data))


def wiki_answers(*, emailuser=None, edit=None, login='Success', emailable=True, talk_text=None):
    def answer(method, params):
        action = params.get('action')
        if action == 'query' and params.get('meta') == 'tokens':
            return {'query': {'tokens': {f"{params['type']}token": 'tok+\\'}}}
        if action == 'login':
            return {'login': {'result': login}}
        if action == 'query' and params.get('list') == 'users':
            user = {'name': params['ususers']}
            if emailable:
                user['emailable'] = True
            return {'query': {'users': [user]}}
        if action == 'query' and params.get('prop') == 'revisions':
            if talk_text is None:
                return {'query': {'pages': [{'missing': True}]}}
            return {'query': {'pages': [{'revisions': [{'slots': {'main': {'content': talk_text}}}]}]}}
        if action == 'emailuser':
            return emailuser or {'emailuser': {'result': 'Success'}}
        if action == 'edit':
            return edit or {'edit': {'result': 'Success', 'newrevid': 42}}
        raise AssertionError(f'unexpected call {params}')
    return answer


def make_client(answer, wiki='nlwiki', credentials=BotCredentials('ProtoWikiBot@r', 'pw')):
    session = FakeSession(answer)
    client = WikiBotClient(wiki, credentials=credentials, user_agent='test-agent',
                           session_factory=lambda: session)
    return client, session


def test_send_email_logs_in_then_posts_with_csrf_token_and_maxlag():
    client, session = make_client(wiki_answers())
    client.send_email('Tester', subject='S', text='T')
    posts = [call for call in session.calls if call[0] == 'POST']
    assert [call[2]['action'] for call in posts] == ['login', 'emailuser']
    assert posts[0][2]['lgname'] == 'ProtoWikiBot@r'
    email = posts[1][2]
    assert email['token'] == 'tok+\\' and email['maxlag'] == 5 and email['assert'] == 'user'
    assert session.calls[0][1] == 'https://nl.wikipedia.org/w/api.php'
    assert session.headers['User-Agent'] == 'test-agent'


def test_post_talk_section_adds_a_new_section_and_returns_the_revision():
    client, session = make_client(wiki_answers())
    assert client.post_talk_section('Tester', title='T', text='B', summary='S') == 42
    edit = session.calls[-1][2]
    assert edit['title'] == 'User talk:Tester' and edit['section'] == 'new'


def test_failed_login_is_an_api_error():
    client, _ = make_client(wiki_answers(login='WrongPass'))
    with pytest.raises(WikiBotError) as raised:
        client.send_email('Tester', subject='S', text='T')
    assert raised.value.reason == API_ERROR and raised.value.code == 'login_wrongpass'


def test_no_credentials_never_calls_the_wiki_to_write():
    client, session = make_client(wiki_answers(), credentials=None)
    with pytest.raises(WikiBotError) as raised:
        client.send_email('Tester', subject='S', text='T')
    assert raised.value.code == 'no_credentials'
    assert not [call for call in session.calls if call[0] == 'POST']


@pytest.mark.parametrize('code, reason', [
    ('nowikiemail', NOT_EMAILABLE), ('noemail', NOT_EMAILABLE), ('ratelimited', THROTTLED),
    ('blocked', BLOCKED), ('blockedfrommail', BLOCKED), ('maxlag', API_ERROR),
])
def test_mediawiki_errors_map_to_reason_codes(code, reason):
    client, _ = make_client(wiki_answers(emailuser={'error': {'code': code}}))
    with pytest.raises(WikiBotError) as raised:
        client.send_email('Tester', subject='S', text='T')
    assert raised.value.reason == reason and raised.value.code == code


def test_network_failure_is_an_api_error():
    class Broken(FakeSession):
        def get(self, url, params, timeout):
            raise requests.ConnectionError('down')
    session = Broken(None)
    client = WikiBotClient('metawiki', credentials=None, user_agent='x',
                           session_factory=lambda: session)
    with pytest.raises(WikiBotError) as raised:
        client.is_emailable('Tester')
    assert raised.value.reason == API_ERROR


def test_emailable_and_talk_page_checks():
    client, _ = make_client(wiki_answers(emailable=False, talk_text='{{nobots}}'))
    assert client.is_emailable('Tester') is False
    assert client.talk_page_allows_bot('Tester') is False
    client, _ = make_client(wiki_answers())
    assert client.is_emailable('Tester') is True
    assert client.talk_page_allows_bot('Tester') is True   # no talk page yet


def test_unknown_wiki_is_refused():
    with pytest.raises(ValueError):
        WikiBotClient('enwiki', credentials=None, user_agent='x')
