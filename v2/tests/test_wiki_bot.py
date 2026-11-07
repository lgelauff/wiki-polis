"""The Proto bot's MediaWiki client (#577): exclusion templates, login, sends, error mapping."""

import pytest
import requests

from services.wiki_bot import (
    API_ERROR, BLOCKED, LAGGED, NOT_EMAILABLE, OUTCOME_UNKNOWN, THROTTLED, BotCredentials,
    WikiBotClient, WikiBotError, bot_allowed,
)


@pytest.mark.parametrize('text, allowed', [
    ('', True),
    ('Hello, see you.', True),
    ('{{nobots}}', False),
    ('{{ NoBots }}', False),
    ('{{bots}}', True),
    ('{{bots|deny=all}}', False),
    ('{{bots|deny=SomeOtherBot, Protowikibot}}', False),
    ('{{bots|deny=SomeOtherBot}}', True),
    ('{{bots|allow=none}}', False),
    ('{{bots|allow=all}}', True),
    ('{{bots|allow=Protowikibot}}', True),
    ('{{bots|allow=SomeOtherBot}}', False),
    ('{{bots|optout=all}}', False),
    ('{{bots|optout=nosource}}', True),
    ('{{bots}} and later {{bots|deny=Protowikibot}}', False),
    ('{{bots|deny=Proto_Wiki_Bot}}', True),
    ('{{bots|deny=protoWikiBot}}', False),
])
def test_bot_exclusion_templates(text, allowed):
    assert bot_allowed(text, 'Protowikibot') is allowed


def test_bot_password_suffix_is_ignored_when_matching_names():
    assert bot_allowed('{{bots|deny=Protowikibot}}', 'Protowikibot@reminders') is False


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.ok = status < 400
        self.headers = headers or {}

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
        self.closed = False
        self._answer = answer

    def close(self):
        self.closed = True

    @staticmethod
    def _respond(answer):
        return answer if isinstance(answer, FakeResponse) else FakeResponse(answer)

    def get(self, url, params, timeout):
        self.calls.append(('GET', url, dict(params)))
        return self._respond(self._answer('GET', params))

    def post(self, url, data, timeout):
        self.calls.append(('POST', url, dict(data)))
        return self._respond(self._answer('POST', data))


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
            if callable(emailuser):
                return emailuser()
            return emailuser or {'emailuser': {'result': 'Success'}}
        if action == 'edit':
            return edit or {'edit': {'result': 'Success', 'newrevid': 42}}
        raise AssertionError(f'unexpected call {params}')
    return answer


def make_client(answer, wiki='nlwiki', credentials=BotCredentials('Protowikibot@r', 'pw'),
                sleeps=None):
    session = FakeSession(answer)
    client = WikiBotClient(wiki, credentials=credentials, user_agent='test-agent',
                           session_factory=lambda: session,
                           sleep=(sleeps.append if sleeps is not None else lambda _: None))
    return client, session


def test_send_email_logs_in_then_posts_with_csrf_token_and_maxlag():
    client, session = make_client(wiki_answers())
    client.send_email('Tester', subject='S', text='T')
    posts = [call for call in session.calls if call[0] == 'POST']
    assert [call[2]['action'] for call in posts] == ['login', 'emailuser']
    assert posts[0][2]['lgname'] == 'Protowikibot@r'
    email = posts[1][2]
    assert email['token'] == 'tok+\\' and email['maxlag'] == 5 and email['assert'] == 'user'
    assert session.calls[0][1] == 'https://nl.wikipedia.org/w/api.php'
    assert session.headers['User-Agent'] == 'test-agent'


def test_post_talk_section_adds_a_new_section_and_returns_the_revision():
    client, session = make_client(wiki_answers())
    assert client.post_talk_section('Tester', title='T', text='B', summary='S') == 42
    edit = session.calls[-1][2]
    assert edit['title'] == 'User talk:Tester' and edit['section'] == 'new'
    assert edit['redirect'] == '1'   # a renamed account's talk page redirects


def test_talk_page_check_follows_a_redirect():
    client, session = make_client(wiki_answers())
    client.talk_page_allows_bot('Tester')
    assert session.calls[-1][2]['redirects'] == '1'


def maxlag(retry_after='3'):
    return FakeResponse({'error': {'code': 'maxlag'}}, status=503,
                        headers={'Retry-After': retry_after})


def test_maxlag_waits_and_retries_the_write():
    answers = iter([maxlag(), {'emailuser': {'result': 'Success'}}])
    sleeps = []
    client, session = make_client(wiki_answers(emailuser=lambda: next(answers)), sleeps=sleeps)
    client.send_email('Tester', subject='S', text='T')
    assert sleeps == [3.0]
    assert [c[2]['action'] for c in session.calls if c[0] == 'POST'] == [
        'login', 'emailuser', 'emailuser']


def test_maxlag_that_does_not_clear_is_lagged_and_waits_are_capped():
    sleeps = []
    client, _ = make_client(wiki_answers(emailuser=lambda: maxlag('120')), sleeps=sleeps)
    with pytest.raises(WikiBotError) as raised:
        client.send_email('Tester', subject='S', text='T')
    assert raised.value.reason == LAGGED
    assert sleeps == [5.0, 5.0]


def test_a_write_that_times_out_has_an_unknown_outcome():
    def timeout():
        raise requests.ReadTimeout('slow')
    client, _ = make_client(wiki_answers(emailuser=timeout))
    with pytest.raises(WikiBotError) as raised:
        client.send_email('Tester', subject='S', text='T')
    assert raised.value.reason == OUTCOME_UNKNOWN and raised.value.code == 'timeout'


def test_a_write_whose_connection_never_opened_is_a_plain_error():
    def refused():
        raise requests.ConnectTimeout('no route')
    client, _ = make_client(wiki_answers(emailuser=refused))
    with pytest.raises(WikiBotError) as raised:
        client.send_email('Tester', subject='S', text='T')
    assert raised.value.reason == API_ERROR


def test_a_read_that_times_out_is_a_plain_error():
    class Slow(FakeSession):
        def get(self, url, params, timeout):
            raise requests.ReadTimeout('slow')
    session = Slow(None)
    client = WikiBotClient('nlwiki', credentials=None, user_agent='x',
                           session_factory=lambda: session)
    with pytest.raises(WikiBotError) as raised:
        client.is_emailable('Tester')
    assert raised.value.reason == API_ERROR


def test_client_closes_its_session():
    client, session = make_client(wiki_answers())
    with client:
        client.is_emailable('Tester')
    assert session.closed


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
    ('blocked', BLOCKED), ('blockedfrommail', BLOCKED), ('badtoken', API_ERROR),
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


def test_a_plain_account_name_is_refused_before_contacting_the_wiki():
    client, session = make_client(wiki_answers(), credentials=BotCredentials('Protowikibot', 'pw'))
    with pytest.raises(WikiBotError) as raised:
        client.send_email('Tester', subject='S', text='T')
    assert raised.value.code == 'not_a_bot_password'
    assert not [call for call in session.calls if call[0] == 'POST']
