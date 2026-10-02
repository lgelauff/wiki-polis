"""Repro for #341 — the join-page consent tick is enforced client-side only.

The join page (`participation-entry-page.tsx`, `JoinPage`) renders a
`required` checkbox named `consent` and never sends it: the join command it calls
passes only `pseudonym` / `notifyEmail` / `notifyTalkPage`. The server route
`POST /api/v1/conversations/<slug>/participation` validates exactly those three
fields and has no consent field at all, so a join submitted without the tick —
a modified request, an extension, an automated client — is accepted and creates
the participation, carrying the irrevocable CC0 public-domain licence grant the
tick is supposed to gate.

These tests go through the real HTTP route with the Flask test client (no mocks
of the code under test), so they keep passing once the server-side check lands.

Known bug: the failing tests are marked xfail(strict=True). When the fix lands they pass,
strict mode turns that into a failure, and the fix removes the marker.
"""

import pytest

@pytest.mark.xfail(strict=True, raises=AssertionError, reason='#341: join consent is not checked by the server yet')
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


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='#341: join consent is not checked by the server yet')
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


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='#341: join consent is not checked by the server yet')
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
