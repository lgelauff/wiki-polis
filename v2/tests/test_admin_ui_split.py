"""Tests for #47: admin/participant UI split with visual mode indicator."""
import hashlib

import pytest

from db import AdminRole, Conversation, Participant, Participation, db


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _xid(uid):
    return hashlib.sha256(str(uid).encode()).hexdigest()


def _login(client, username):
    p = Participant.query.filter_by(mw_username=username).first()
    xid = p.xid if p else hashlib.sha256(username.encode()).hexdigest()
    with client.session_transaction() as sess:
        sess['username'] = username
        sess['xid'] = xid
        sess['emailable'] = True


@pytest.fixture
def conv(app):
    c = Conversation(
        slug='ui-test', polis_id='abc1234567',
        title='UI Test Conversation', active=True, access_policy='public',
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def admin_p(app):
    p = Participant(mw_user_id=77701, mw_username='admin47', xid=_xid(77701),
                    is_global_admin=True)
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def regular_p(app):
    p = Participant(mw_user_id=77702, mw_username='user47', xid=_xid(77702))
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def mod_p(app, conv):
    p = Participant(mw_user_id=77703, mw_username='mod47', xid=_xid(77703))
    db.session.add(p)
    db.session.flush()
    role = AdminRole(participant_id=p.id, conversation_id=conv.id, role='moderator')
    db.session.add(role)
    db.session.commit()
    return p


def _enroll(participant, conv):
    """Create a Participation so /c/<slug> doesn't redirect to /accept."""
    part = Participation(participant_id=participant.id,
                         conversation_id=conv.id, pseudonym='p', new_stmt_ids=[])
    db.session.add(part)
    db.session.commit()


@pytest.fixture
def admin_client(client, admin_p):
    _login(client, 'admin47')
    return client


@pytest.fixture
def regular_client(client, regular_p):
    _login(client, 'user47')
    return client


@pytest.fixture
def mod_client(client, mod_p):
    _login(client, 'mod47')
    return client


# ── Admin header tint ─────────────────────────────────────────────────────────

def test_admin_panel_has_admin_class(admin_client):
    resp = admin_client.get('/admin')
    assert resp.status_code == 200
    assert b'header--admin' in resp.data


def test_admin_conversation_has_admin_class(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'header--admin' in resp.data


def test_admin_featured_has_admin_class(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}/featured')
    assert resp.status_code == 200
    assert b'header--admin' in resp.data


def test_admin_statements_has_admin_class(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}/statements')
    assert resp.status_code == 200
    assert b'header--admin' in resp.data


def test_admin_invites_has_admin_class(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}/invites')
    assert resp.status_code == 200
    assert b'header--admin' in resp.data


# ── Old inline back-links are gone ────────────────────────────────────────────

def test_admin_conversation_no_inline_backlink(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert '← admin panel'.encode() not in resp.data


def test_admin_statements_no_inline_backlink(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}/statements')
    assert '← admin'.encode() not in resp.data


def test_admin_invites_no_inline_backlink(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}/invites')
    assert '← back to admin'.encode() not in resp.data


# ── Manage link on conversation.html ─────────────────────────────────────────

def test_moderator_sees_manage_link(mod_client, mod_p, conv):
    _enroll(mod_p, conv)
    resp = mod_client.get(f'/c/{conv.slug}')
    assert resp.status_code == 200
    assert '← Manage'.encode() in resp.data


def test_admin_sees_manage_link(admin_client, admin_p, conv):
    _enroll(admin_p, conv)
    resp = admin_client.get(f'/c/{conv.slug}')
    assert resp.status_code == 200
    assert '← Manage'.encode() in resp.data


def test_regular_user_no_manage_link(regular_client, regular_p, conv):
    _enroll(regular_p, conv)
    resp = regular_client.get(f'/c/{conv.slug}')
    assert resp.status_code == 200
    assert '← Manage'.encode() not in resp.data
