"""Choosing a consultation's eligibility policy from canivote's list (#530)."""

from urllib.parse import unquote

import pytest
import requests

from db import AdminRole, Conversation, Participant, db
from services import eligibility_policies
from services.eligibility_policies import (
    EligibilityPolicyRefused, PolicyCache, fetch_policies, resolve_policy_choice,
)
from tests.conftest import CANIVOTE_POLICIES, login


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _unreachable(base_url, *, user_agent, get=None):
    """`fetch_policies` while canivote is configured but cannot be reached."""
    raise requests.ConnectionError('canivote is down')


def _canivote(details, *, listed=None):
    """A fake `requests.get` for canivote: `/policies` and `/policies/<id>`."""
    calls = []

    def get(url, *, headers, timeout):
        calls.append(url)
        assert headers['User-Agent'] == 'test-agent'
        if url.endswith('/policies'):
            ids = listed if listed is not None else list(details)
            return _Response({'policies': [
                {'id': policy_id, 'title': f'Title of {policy_id}', 'wiki': 'nl.wikipedia.org'}
                for policy_id in ids
            ]})
        policy_id = unquote(url.rsplit('/', 1)[1])
        detail = details.get(policy_id)
        if isinstance(detail, Exception):
            raise detail
        return _Response(detail, 200 if detail is not None else 404)

    get.calls = calls
    return get


# ── The list, as read from canivote ───────────────────────────────────────────

def test_fetch_lists_each_policy_with_its_rules_once():
    rule = {'metric': 'is_blocked', 'wiki': 'nl.wikipedia.org', 'operator': 'is', 'value': False}
    get = _canivote({'nlwiki-stemprocedure': {
        'rules': [
            {**rule, 'source': 'platform'},
            {**rule, 'source': 'policy'},
            {'metric': 'edit_count', 'wiki': 'nl.wikipedia.org', 'operator': 'more_than',
             'value': 100, 'offset': 3, 'source': 'policy'},
        ],
        'sources': ['https://nl.wikipedia.org/wiki/Wikipedia:Stemprocedure',
                    'javascript:alert(1)'],
    }})

    policies = fetch_policies('https://canivote.example/', user_agent='test-agent', get=get)

    assert get.calls == ['https://canivote.example/policies',
                         'https://canivote.example/policies/nlwiki-stemprocedure']
    assert policies == [{
        'id': 'nlwiki-stemprocedure',
        'title': 'Title of nlwiki-stemprocedure',
        'wiki': 'nl.wikipedia.org',
        # The platform's and the policy's copy of one rule are shown once; keys the console
        # does not render (`source`, `offset`) are dropped.
        'rules': [rule, {'metric': 'edit_count', 'wiki': 'nl.wikipedia.org',
                         'operator': 'more_than', 'value': 100}],
        'sources': ['https://nl.wikipedia.org/wiki/Wikipedia:Stemprocedure'],
    }]


def test_a_policy_whose_detail_fails_is_listed_without_rules():
    get = _canivote({'meta-global': requests.ConnectionError('down'),
                     'gone': None})

    policies = fetch_policies('https://canivote.example', user_agent='test-agent', get=get)

    assert [(policy['id'], policy['rules']) for policy in policies] == [
        ('meta-global', None), ('gone', None),
    ]


def test_cache_keeps_the_list_ten_minutes_and_a_failure_one(monkeypatch):
    now = [1000.0]
    answers = [requests.ConnectionError('down'), [{'id': 'meta-global'}]]
    fetches = []

    def fake_fetch(base_url, *, user_agent):
        fetches.append(base_url)
        answer = answers.pop(0) if answers else [{'id': 'later'}]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(eligibility_policies, 'fetch_policies', fake_fetch)
    cache = PolicyCache(clock=lambda: now[0])

    assert cache.get('', user_agent='ua') is None
    assert fetches == []  # not configured: nothing to ask
    assert cache.get('https://canivote.example', user_agent='ua') is None
    now[0] += 59
    assert cache.get('https://canivote.example', user_agent='ua') is None
    assert len(fetches) == 1  # the failure is remembered for a minute
    now[0] += 2
    assert cache.get('https://canivote.example', user_agent='ua') == [{'id': 'meta-global'}]
    now[0] += 599
    assert cache.get('https://canivote.example', user_agent='ua') == [{'id': 'meta-global'}]
    assert len(fetches) == 2
    now[0] += 2
    assert cache.get('https://canivote.example', user_agent='ua') == [{'id': 'later'}]


def test_one_read_stops_at_the_deadline():
    """A slow canivote costs at most DEADLINE_SECONDS; the rest is listed without rules."""
    now = [0.0]
    timeouts = []

    def slow_get(url, *, headers, timeout):
        timeouts.append(timeout)
        now[0] += 3  # every request takes three seconds
        if url.endswith('/policies'):
            return _Response({'policies': [{'id': f'p{index}'} for index in range(5)]})
        return _Response({'rules': [{'metric': 'is_globally_locked', 'operator': 'is',
                                     'value': False}], 'sources': []})

    policies = fetch_policies('https://canivote.example', user_agent='test-agent',
                              get=slow_get, clock=lambda: now[0])

    assert now[0] <= eligibility_policies.DEADLINE_SECONDS + eligibility_policies.TIMEOUT_SECONDS
    assert [policy['rules'] is not None for policy in policies] == [True, True, False, False, False]
    # The last detail request is given only the time left, not a full timeout.
    assert timeouts[-1] == 2


def test_concurrent_misses_read_canivote_once(monkeypatch):
    import threading
    started, release = threading.Event(), threading.Event()
    fetches = []

    def slow_fetch(base_url, *, user_agent):
        fetches.append(base_url)
        started.set()
        release.wait(5)
        return [{'id': 'meta-global'}]

    monkeypatch.setattr(eligibility_policies, 'fetch_policies', slow_fetch)
    cache = PolicyCache()
    answers = []
    threads = [threading.Thread(target=lambda: answers.append(
        cache.get('https://canivote.example', user_agent='ua'))) for _ in range(3)]
    threads[0].start()
    started.wait(5)
    for thread in threads[1:]:
        thread.start()
    release.set()
    for thread in threads:
        thread.join(5)

    assert fetches == ['https://canivote.example']
    assert answers == [[{'id': 'meta-global'}]] * 3


def test_a_policy_id_is_quoted_in_the_detail_url():
    get = _canivote({'odd/../id?x': {'rules': [], 'sources': []}})

    fetch_policies('https://canivote.example', user_agent='test-agent', get=get)

    assert get.calls[1] == 'https://canivote.example/policies/odd%2F..%2Fid%3Fx'


# ── What a save stores ────────────────────────────────────────────────────────

def _listed():
    return [dict(policy) for policy in CANIVOTE_POLICIES]


def _down():
    return None


@pytest.mark.parametrize('requested, label, stored, policies, expected', [
    # No policy: no label either.
    ('', 'Left over', 'meta-global', _listed, ('', '')),
    # A listed policy; an empty label becomes its title, an organizer's own label stays.
    ('nlwiki-stemprocedure', '', None, _listed,
     ('nlwiki-stemprocedure', 'Voting eligibility on Dutch Wikipedia')),
    ('nlwiki-stemprocedure', '  Stemgerechtigd op nl.wikipedia ', None, _listed,
     ('nlwiki-stemprocedure', 'Stemgerechtigd op nl.wikipedia')),
    # The stored id sent back unchanged is kept, even when canivote no longer lists it or
    # cannot be reached, so a Save of other fields is never refused because of it.
    ('old-policy', 'Old label', 'old-policy', _listed, ('old-policy', 'Old label')),
    ('meta-global', 'Kept', 'meta-global', _down, ('meta-global', 'Kept')),
    ('old-policy', '', 'old-policy', _down, ('old-policy', '')),
])
def test_resolve_policy_choice_stores(requested, label, stored, policies, expected):
    choice = resolve_policy_choice(
        requested_id=requested, requested_label=label, stored_id=stored, policies=policies,
    )
    assert (choice.event_id, choice.label) == expected


@pytest.mark.parametrize('requested, stored, policies, configured, code', [
    ('nlwiki-stemprocdure', None, _listed, True, 'eligibility_policy_unlisted'),
    ('nlwiki-stemprocedure', 'meta-global', _down, True, 'eligibility_policies_unavailable'),
    ('nlwiki-stemprocedure', None, _down, False, 'eligibility_policies_not_configured'),
])
def test_resolve_policy_choice_refuses(requested, stored, policies, configured, code):
    with pytest.raises(EligibilityPolicyRefused) as refused:
        resolve_policy_choice(
            requested_id=requested, requested_label='', stored_id=stored, policies=policies,
            configured=configured,
        )
    assert refused.value.field == 'eligibilityEventId'
    # The code is what the console puts in words (#454).
    assert refused.value.code == code


# ── GET /admin/eligibility-policies ───────────────────────────────────────────

POLICIES_URL = '/api/v1/admin/eligibility-policies'


def test_policy_list_needs_a_sign_in(client, canivote_policies):
    assert client.get(POLICIES_URL).status_code == 401


def test_policy_list_is_refused_to_a_moderator_who_organizes_nothing(
    client, conversation, participant, canivote_policies,
):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conversation.id, role='moderator'))
    db.session.commit()
    login(client, 'testuser')

    assert client.get(POLICIES_URL).status_code == 403
    assert canivote_policies == []


def test_policy_list_for_an_organizer(client, conversation, participant, canivote_policies):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conversation.id, role='organizer'))
    db.session.commit()
    login(client, 'testuser')

    response = client.get(POLICIES_URL)

    assert response.status_code == 200
    assert response.headers['Cache-Control'].startswith('no-store')
    data = response.get_json()['data']
    assert data['available'] is True
    assert [policy['id'] for policy in data['policies']] == [
        'nlwiki-stemprocedure', 'meta-global',
    ]
    # A second read within ten minutes is served from the cache.
    client.get(POLICIES_URL)
    assert canivote_policies == ['https://canivote.example']


def test_policy_list_says_when_canivote_is_not_configured(admin_client, app):
    app.config['ACCOUNT_ELIGIBILITY_URL'] = ''

    data = admin_client.get(POLICIES_URL).get_json()['data']

    assert data == {'available': False, 'configured': False, 'policies': []}


def test_policy_list_says_when_canivote_is_down(admin_client, app, monkeypatch):
    app.config['ACCOUNT_ELIGIBILITY_URL'] = 'https://canivote.example'
    monkeypatch.setattr(eligibility_policies, 'fetch_policies', _unreachable)

    data = admin_client.get(POLICIES_URL).get_json()['data']

    assert data == {'available': False, 'configured': True, 'policies': []}


def test_openapi_documents_the_policy_list(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths']['/admin/eligibility-policies']['get']
    assert set(operation['responses']) == {'200', '401', '403'}
    policy = spec['components']['schemas']['EligibilityPolicy']
    assert set(policy['required']) == set(CANIVOTE_POLICIES[0])


# ── Settings: read and save ───────────────────────────────────────────────────

def _settings_url(conversation):
    return f'/api/v1/admin/conversations/{conversation.id}/settings'


def _settings_body(conversation, **overrides):
    body = {
        'title': conversation.title, 'introHtml': '', 'outroHtml': '',
        'gated': False, 'gatingType': None, 'announce': False, 'information': False,
        'resultsShared': False, 'showUsernames': False, 'accessRequestText': None,
        'eligibilityEventId': conversation.eligibility_event_id or '',
        'eligibilityLabel': conversation.eligibility_label or '',
        'recommendationTier': 'medium',
    }
    body.update(overrides)
    return body


def _moderator_client(client, conversation, participant):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conversation.id, role='moderator'))
    db.session.commit()
    login(client, 'testuser')
    return client


def test_settings_without_a_policy_do_not_ask_canivote(
    client, conversation, participant, canivote_policies,
):
    moderator = _moderator_client(client, conversation, participant)

    eligibility = moderator.get(_settings_url(conversation)).get_json()['data']['eligibility']

    assert eligibility['policy'] is None
    assert canivote_policies == []


def test_an_editor_s_settings_never_wait_on_canivote(
    admin_client, conversation, canivote_policies,
):
    """An editor reads the list from its own endpoint; Settings itself does not ask."""
    conversation.eligibility_event_id = 'nlwiki-stemprocedure'
    db.session.commit()

    eligibility = admin_client.get(_settings_url(conversation)).get_json()['data']['eligibility']

    assert eligibility['eventId'] == 'nlwiki-stemprocedure'
    assert eligibility['policy'] is None
    assert canivote_policies == []


def test_a_moderator_reads_the_stored_policy_and_its_rules(
    client, conversation, participant, canivote_policies,
):
    conversation.eligibility_event_id = 'nlwiki-stemprocedure'
    conversation.eligibility_label = 'Stemgerechtigd'
    db.session.commit()
    moderator = _moderator_client(client, conversation, participant)

    eligibility = moderator.get(_settings_url(conversation)).get_json()['data']['eligibility']

    assert eligibility['label'] == 'Stemgerechtigd'
    assert eligibility['policy'] == CANIVOTE_POLICIES[0]


def test_a_moderator_gets_no_policy_for_a_stored_id_canivote_does_not_have(
    client, conversation, participant, canivote_policies,
):
    conversation.eligibility_event_id = 'typed-by-hand'
    db.session.commit()
    moderator = _moderator_client(client, conversation, participant)

    eligibility = moderator.get(_settings_url(conversation)).get_json()['data']['eligibility']

    assert eligibility['eventId'] == 'typed-by-hand'
    assert eligibility['policy'] is None


def test_choosing_a_policy_stores_it_with_its_title_as_label(
    admin_client, conversation, canivote_policies,
):
    response = admin_client.put(_settings_url(conversation), json=_settings_body(
        conversation, eligibilityEventId='nlwiki-stemprocedure', eligibilityLabel='',
    ))

    assert response.status_code == 200
    assert conversation.eligibility_event_id == 'nlwiki-stemprocedure'
    assert conversation.eligibility_label == 'Voting eligibility on Dutch Wikipedia'


def test_the_organizers_own_label_is_kept(admin_client, conversation, canivote_policies):
    response = admin_client.put(_settings_url(conversation), json=_settings_body(
        conversation, eligibilityEventId='nlwiki-stemprocedure',
        eligibilityLabel='Stemgerechtigd op de Nederlandstalige Wikipedia',
    ))

    assert response.status_code == 200
    assert conversation.eligibility_label == 'Stemgerechtigd op de Nederlandstalige Wikipedia'


def test_an_id_not_on_the_list_is_refused_and_nothing_changes(
    admin_client, conversation, canivote_policies,
):
    response = admin_client.put(_settings_url(conversation), json=_settings_body(
        conversation, title='Changed too', eligibilityEventId='nlwiki-stemprocdure',
    ))

    assert response.status_code == 400
    error = response.get_json()['error']
    assert error['code'] == 'validation_failed'
    assert error['details']['codes'] == {'eligibilityEventId': 'eligibility_policy_unlisted'}
    assert set(error['details']['fields']) == {'eligibilityEventId'}
    db.session.refresh(conversation)
    assert conversation.eligibility_event_id is None
    assert conversation.title == 'Test Conversation'


def test_a_new_policy_is_refused_when_canivote_is_not_configured(
    admin_client, app, conversation,
):
    app.config['ACCOUNT_ELIGIBILITY_URL'] = ''

    response = admin_client.put(_settings_url(conversation), json=_settings_body(
        conversation, eligibilityEventId='nlwiki-stemprocedure',
    ))

    assert response.status_code == 400
    assert response.get_json()['error']['details']['codes'] == {
        'eligibilityEventId': 'eligibility_policies_not_configured',
    }


def test_the_stored_policy_does_not_block_other_changes_while_canivote_is_down(
    admin_client, app, conversation,
):
    conversation.eligibility_event_id = 'nlwiki-stemprocedure'
    conversation.eligibility_label = 'Stemgerechtigd'
    db.session.commit()
    app.config['ACCOUNT_ELIGIBILITY_URL'] = ''

    response = admin_client.put(_settings_url(conversation), json=_settings_body(
        conversation, title='A new title',
    ))

    assert response.status_code == 200
    assert conversation.title == 'A new title'
    assert conversation.eligibility_event_id == 'nlwiki-stemprocedure'


def test_no_policy_clears_the_label(admin_client, conversation, canivote_policies):
    conversation.eligibility_event_id = 'meta-global'
    conversation.eligibility_label = 'Not blocked'
    db.session.commit()

    response = admin_client.put(_settings_url(conversation), json=_settings_body(
        conversation, eligibilityEventId='', eligibilityLabel='Not blocked',
    ))

    assert response.status_code == 200
    assert conversation.eligibility_event_id is None
    assert conversation.eligibility_label is None


def test_the_policy_may_change_after_explore_opens(
    admin_client, conversation, canivote_policies,
):
    """Not locked (owner, 2026-10-15): the lock stays with #408."""
    conversation.eligibility_event_id = 'meta-global'
    conversation.phase_submission = True
    db.session.commit()

    response = admin_client.put(_settings_url(conversation), json=_settings_body(
        conversation, eligibilityEventId='nlwiki-stemprocedure', eligibilityLabel='',
    ))

    assert response.status_code == 200
    assert conversation.eligibility_event_id == 'nlwiki-stemprocedure'


def test_the_invitation_list_clears_even_an_unlisted_policy(
    admin_client, conversation, canivote_policies,
):
    conversation.eligibility_event_id = 'typed-by-hand'
    db.session.commit()

    response = admin_client.put(_settings_url(conversation), json=_settings_body(
        conversation, gated=True, gatingType='invite_only',
        eligibilityEventId='something-else',
    ))

    assert response.status_code == 200
    assert conversation.eligibility_event_id is None


# ── New consultation on /site-admin ───────────────────────────────────────────

def _creation_body(**overrides):
    body = {
        'slug': 'with-a-policy', 'title': 'With a policy', 'introHtml': '', 'outroHtml': '',
        'accessPolicy': 'public', 'phaseRoute': 'default_7',
        'eligibilityEventId': '', 'eligibilityLabel': '', 'polisId': 'manual12345',
    }
    body.update(overrides)
    return body


def test_a_new_consultation_takes_a_listed_policy(admin_client, canivote_policies):
    response = admin_client.post('/api/v1/admin/conversations', json=_creation_body(
        eligibilityEventId='meta-global',
    ))

    assert response.status_code == 201
    conversation = Conversation.query.filter_by(slug='with-a-policy').one()
    assert conversation.eligibility_event_id == 'meta-global'
    assert conversation.eligibility_label == 'Not blocked anywhere in the movement'


def test_a_new_consultation_refuses_an_unlisted_policy(admin_client, canivote_policies):
    response = admin_client.post('/api/v1/admin/conversations', json=_creation_body(
        eligibilityEventId='typed-by-hand', eligibilityLabel='Anything',
    ))

    assert response.status_code == 400
    assert response.get_json()['error']['details']['codes'] == {
        'eligibilityEventId': 'eligibility_policy_unlisted',
    }
    assert Conversation.query.filter_by(slug='with-a-policy').first() is None
    assert Participant.query.count() == 1


def test_the_invitation_list_clears_the_policy_before_it_is_checked(
    admin_client, canivote_policies,
):
    """As a settings save does: a policy left in the form is not checked, and not stored,
    for a consultation the invitation list admits to."""
    response = admin_client.post('/api/v1/admin/conversations', json=_creation_body(
        accessPolicy='invite_only', eligibilityEventId='typed-by-hand',
        eligibilityLabel='Anything',
    ))

    assert response.status_code == 201
    conversation = Conversation.query.filter_by(slug='with-a-policy').one()
    assert conversation.eligibility_event_id is None
    assert conversation.eligibility_label is None
    assert canivote_policies == []


def test_a_new_consultation_says_when_canivote_is_not_configured(admin_client, app):
    """The create path passes the server's configuration to the check, as Settings does."""
    app.config['ACCOUNT_ELIGIBILITY_URL'] = ''

    response = admin_client.post('/api/v1/admin/conversations', json=_creation_body(
        eligibilityEventId='meta-global',
    ))

    assert response.status_code == 400
    assert response.get_json()['error']['details']['codes'] == {
        'eligibilityEventId': 'eligibility_policies_not_configured',
    }
