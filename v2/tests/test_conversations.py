"""Tests for the conversation listing, accept, and participation flows."""
import pytest

from db import (Conversation, ConversationInvite, Participant, Participation,
                db)

from tests.conftest import login


@pytest.fixture
def conv(app):
    c = Conversation(
        slug='test-conv', polis_id='abc1234567',
        title='Test Conversation', active=True, access_policy='public',
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def participation(app, participant, conv):
    p = Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym='happy-fox',
    )
    db.session.add(p)
    db.session.commit()
    return p


# ── Index ─────────────────────────────────────────────────────────────────────

def test_index_unauthenticated_shows_public_conversations(client, conv):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Test Conversation' in resp.data


def test_index_unauthenticated_hides_paused_conversations(client, app):
    c = Conversation(slug='paused', polis_id='xyz9876543', title='Paused Conv',
                     active=True, paused=True, access_policy='public')
    db.session.add(c)
    db.session.commit()
    resp = client.get('/')
    assert b'Paused Conv' not in resp.data


def test_index_authenticated_shows_joined_conversations(auth_client, participation, conv):
    resp = auth_client.get('/')
    assert resp.status_code == 200
    assert b'Test Conversation' in resp.data


# ── Accept ────────────────────────────────────────────────────────────────────

def test_accept_get_renders_pseudonym_options(auth_client, conv):
    resp = auth_client.get('/accept/test-conv')
    assert resp.status_code == 200
    assert b'pseudonym' in resp.data.lower()


def test_accept_get_already_joined_redirects(auth_client, conv, participation):
    resp = auth_client.get('/accept/test-conv')
    assert resp.status_code == 302
    assert '/c/test-conv' in resp.headers['Location']


def test_accept_post_creates_participation(auth_client, conv, participant):
    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'silly-goat'})
    assert resp.status_code == 302
    p = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first()
    assert p is not None
    assert p.pseudonym == 'silly-goat'


def test_accept_post_invalid_pseudonym_rejected(auth_client, conv):
    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'bad name!'})
    assert resp.status_code == 400


def test_accept_post_pseudonym_too_short_rejected(auth_client, conv):
    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'a-b'})
    assert resp.status_code == 400


def test_accept_post_duplicate_pseudonym_shows_error(auth_client, conv, app):
    """Attempting to claim a pseudonym already in use re-renders with an error."""
    other = Participant(mw_user_id=11111, mw_username='other',
                        xid='o' * 64)
    db.session.add(other)
    db.session.commit()
    taken = Participation(participant_id=other.id, conversation_id=conv.id,
                          pseudonym='taken-name')
    db.session.add(taken)
    db.session.commit()

    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'taken-name'})
    assert resp.status_code == 200
    assert b'taken' in resp.data.lower()


def test_accept_pseudonyms_endpoint_returns_list(auth_client, conv):
    resp = auth_client.get('/accept/test-conv/pseudonyms')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'pseudonyms' in data
    assert len(data['pseudonyms']) == 5
    for name in data['pseudonyms']:
        assert '-' in name


# ── Conversation page ─────────────────────────────────────────────────────────

def test_conversation_without_participation_redirects_to_accept(auth_client, conv):
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 302
    assert '/accept/test-conv' in resp.headers['Location']


def test_conversation_with_participation_renders(auth_client, conv, participation):
    """With a valid participation, the conversation page renders (no redirect)."""
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    # No phases enabled → shows the "nothing available" placeholder.
    assert b'Nothing is available yet' in resp.data


# ── Access control ────────────────────────────────────────────────────────────

def test_invite_only_blocks_uninvited(client, app, participant):
    login(client, 'testuser')
    c = Conversation(slug='private', polis_id='pri1234567', title='Private',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()
    resp = client.get('/accept/private')
    assert resp.status_code == 403


def test_invite_only_allows_invited(client, app, participant):
    login(client, 'testuser')
    c = Conversation(slug='private2', polis_id='pr21234567', title='Private2',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()
    inv = ConversationInvite(conversation_id=c.id, mw_username='testuser')
    db.session.add(inv)
    db.session.commit()
    resp = client.get('/accept/private2')
    assert resp.status_code == 200


def test_invite_only_allows_already_joined(client, app, participant):
    """A participant who already joined can visit even after invite is removed."""
    c = Conversation(slug='private3', polis_id='pr31234567', title='Private3',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()
    part = Participation(participant_id=participant.id,
                         conversation_id=c.id, pseudonym='quick-otter')
    db.session.add(part)
    db.session.commit()
    login(client, 'testuser')
    resp = client.get('/c/private3')
    assert resp.status_code == 200
