"""#341: the join page's consent tick is checked by the server, not only the browser.

The tick on the join page also grants the CC0 public-domain licence on everything the
participant writes, so a join that does not carry it (a modified request, an extension,
an automated client) must be refused, and a join that does must still go through.

These tests go through the real HTTP route with the Flask test client (no mocks of the
code under test). They started as expected-failure repros on test/known-bug-repros.
"""

import pytest


def test_join_without_consent_is_rejected_by_the_server(auth_client, conversation):
    response = auth_client.post(
        '/api/v1/conversations/test-conv/participation',
        json={'pseudonym': 'consent-otter'},
    )

    assert response.status_code == 400, (
        '#341: submitting the join form without ticking the required consent '
        'checkbox must be refused by the server with 400, because the tick also '
        'gates the irrevocable CC0 public-domain licence grant; the request was '
        f'answered with {response.status_code} {response.get_data(as_text=True)!r}.'
    )
    error = response.get_json()['error']
    assert error['code'] == 'validation_failed'
    assert 'consent' in error['details']['fields'], (
        '#341: the 400 must name the missing consent field so the join page can '
        f'show it; got {error["details"]["fields"]!r}.'
    )


def test_join_without_consent_creates_no_participation(auth_client, conversation):
    from db import Participation

    auth_client.post(
        '/api/v1/conversations/test-conv/participation',
        json={'pseudonym': 'consent-otter'},
    )

    assert Participation.query.count() == 0, (
        '#341: a join that never carried the required consent value must not '
        'create a participation row, because no consent was given; '
        f'{Participation.query.count()} row(s) exist.'
    )


def test_join_with_consent_is_accepted(auth_client, conversation):
    """The other half of the contract, so a degenerate "reject everything" fix fails too."""
    response = auth_client.post(
        '/api/v1/conversations/test-conv/participation',
        json={'pseudonym': 'consent-otter', 'consent': True},
    )

    assert response.status_code == 201, (
        '#341: a join that does carry the consent value must be accepted, so '
        'ticking the box lets the participant in; the request was answered with '
        f'{response.status_code} {response.get_data(as_text=True)!r}.'
    )
    assert response.get_json()['data']['pseudonym'] == 'consent-otter'



@pytest.mark.parametrize('value', [False, 0, 1, 'true', 'yes', None, [], {}])
def test_join_with_consent_anything_but_true_is_rejected(auth_client, conversation, value):
    """Only the JSON value true is a tick. 1 == True in Python, so a later `== True` or a
    truthiness check would let 1 or "yes" through; these values pin the exact check."""
    response = auth_client.post(
        '/api/v1/conversations/test-conv/participation',
        json={'pseudonym': 'consent-otter', 'consent': value},
    )

    assert response.status_code == 400
    assert 'consent' in response.get_json()['error']['details']['fields']
