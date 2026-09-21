"""Voucher code generation, redemption, and access provider (#368)."""

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import g

from db import (
    ACCOUNT_KIND_VOUCHER,
    Conversation,
    Participant,
    Participation,
    VoucherBatch,
    VoucherCode,
    db,
)
from services.access import check_access
from services.vouchers import (
    generate_voucher_code,
    generate_voucher_codes,
    lookup_voucher,
    normalize_code,
    redeem_voucher,
    reserve_voucher,
    revoke_voucher,
    voucher_code_hmac,
)


# ── Code generation and normalisation ─────────────────────────────────────────

def test_generated_code_is_12_char_crockford():
    for _ in range(100):
        code = generate_voucher_code()
        assert len(code) == 12
        assert re.match(r'^[0-9A-HJKMNP-TV-Z]{12}$', code), code


def test_generated_codes_are_unique():
    codes = {generate_voucher_code() for _ in range(100)}
    assert len(codes) == 100


def test_normalize_strips_whitespace_and_hyphens():
    assert normalize_code('abc def-ghi') == 'ABCDEFGHI'
    assert normalize_code('  X7F3-K9M2  ') == 'X7F3K9M2'


def test_normalize_is_case_insensitive():
    assert normalize_code('abcdefghijkl') == 'ABCDEFGHIJKL'


# ── HMAC ──────────────────────────────────────────────────────────────────────

def test_hmac_is_scoped_by_conversation_id(app):
    """Same raw code, different conversations → different HMAC."""
    h1 = voucher_code_hmac('X7F3K9M2ABCD', 1)
    h2 = voucher_code_hmac('X7F3K9M2ABCD', 2)
    assert h1 != h2


def test_hmac_is_stable_for_same_input(app):
    a = voucher_code_hmac('X7F3K9M2ABCD', 42)
    b = voucher_code_hmac('X7F3K9M2ABCD', 42)
    assert a == b


# ── Batch generation ──────────────────────────────────────────────────────────

def test_generate_voucher_codes_persists_rows(app, conversation):
    batch = VoucherBatch(conversation_id=conversation.id, label='Test')
    db.session.add(batch)
    db.session.commit()

    codes = generate_voucher_codes(batch, 5)

    assert len(codes) == 5
    assert len(set(codes)) == 5

    rows = VoucherCode.query.filter_by(batch_id=batch.id).all()
    assert len(rows) == 5
    for row in rows:
        assert row.status == 'unused'
        assert row.code_hmac is not None


# ── Lookup and state machine ──────────────────────────────────────────────────

def _make_voucher(conversation, code='X7F3K9M2ABCD', **kwargs):
    batch = VoucherBatch(conversation_id=conversation.id)
    db.session.add(batch)
    db.session.flush()
    voucher = VoucherCode(
        batch_id=batch.id,
        code_hmac=voucher_code_hmac(code, conversation.id),
        **kwargs,
    )
    db.session.add(voucher)
    db.session.commit()
    return voucher


def test_lookup_finds_unused_voucher(app, conversation):
    v = _make_voucher(conversation)
    found = lookup_voucher('X7F3K9M2ABCD', conversation.id)
    assert found is not None
    assert found.id == v.id


def test_lookup_returns_none_for_wrong_code(app, conversation):
    _make_voucher(conversation)
    assert lookup_voucher('ZZZZZZZZZZZZ', conversation.id) is None


def test_lookup_returns_none_for_wrong_conversation(app, conversation):
    _make_voucher(conversation)
    conv2 = Conversation(
        slug='other-conv', polis_id='xyz9876543',
        title='Other', active=True,
    )
    db.session.add(conv2)
    db.session.commit()
    assert lookup_voucher('X7F3K9M2ABCD', conv2.id) is None


def test_reserve_sets_status_and_30_min_expiry(app, conversation):
    v = _make_voucher(conversation)
    reserve_voucher(v)
    db.session.commit()

    assert v.status == 'reserved'
    assert v.reserved_until is not None
    rv = v.reserved_until
    if rv.tzinfo is None:
        rv = rv.replace(tzinfo=timezone.utc)
    delta = rv - datetime.now(timezone.utc)
    assert timedelta(minutes=29) < delta < timedelta(minutes=31)


def test_redeem_marks_status_and_links_participant(app, conversation, participant):
    v = _make_voucher(conversation, status='reserved')
    redeem_voucher(v, participant.id)
    db.session.commit()

    assert v.status == 'redeemed'
    assert v.participant_id == participant.id
    assert v.redeemed_at is not None
    assert v.reserved_until is None


def test_revoke_sets_status_and_timestamp(app, conversation):
    v = _make_voucher(conversation)
    revoke_voucher(v)
    db.session.commit()

    assert v.status == 'revoked'
    assert v.revoked_at is not None


# ── Voucher entry endpoint ────────────────────────────────────────────────────

def test_voucher_page_renders_form(app, client, conversation):
    resp = client.get(f'/{conversation.slug}/v')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Voucher code' in html
    assert conversation.title in html


def test_voucher_page_auto_processes_valid_code_and_redirects(
    app, client, conversation,
):
    code = 'X7F3K9M2ABCD'
    _make_voucher(conversation, code=code)
    resp = client.get(f'/{conversation.slug}/v?v={code}')
    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/{conversation.slug}'
    with client.session_transaction() as sess:
        assert 'xid' in sess


def test_voucher_page_auto_process_shows_error_for_invalid_code(
    app, client, conversation,
):
    resp = client.get(f'/{conversation.slug}/v?v=ZZZZZZZZZZZZ')
    html = resp.data.decode()
    assert 'not valid' in html


def test_voucher_post_redeems_and_redirects(app, client, conversation):
    code = 'X7F3K9M2ABCD'
    _make_voucher(conversation, code=code)
    resp = client.post(f'/{conversation.slug}/v', data={'code': code})
    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/{conversation.slug}'
    with client.session_transaction() as sess:
        assert 'xid' in sess


def test_voucher_post_empty_code_shows_error(app, client, conversation):
    resp = client.post(f'/{conversation.slug}/v', data={'code': ''})
    html = resp.data.decode()
    assert 'Enter a voucher code' in html


def test_voucher_post_invalid_code_shows_error(app, client, conversation):
    resp = client.post(f'/{conversation.slug}/v', data={'code': 'ZZZZZZZZZZZZ'})
    html = resp.data.decode()
    assert 'not valid' in html


def test_voucher_post_expired_code_shows_error(app, client, conversation):
    code = 'X7F3K9M2ABCD'
    _make_voucher(
        conversation, code=code,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    resp = client.post(f'/{conversation.slug}/v', data={'code': code})
    html = resp.data.decode()
    assert 'not valid' in html


def test_voucher_post_revoked_code_shows_error(app, client, conversation):
    code = 'X7F3K9M2ABCD'
    _make_voucher(conversation, code=code, status='revoked')
    resp = client.post(f'/{conversation.slug}/v', data={'code': code})
    html = resp.data.decode()
    assert 'not valid' in html


def test_voucher_create_participant_is_conversation_scoped(app, client, conversation):
    code = 'X7F3K9M2ABCD'
    _make_voucher(conversation, code=code)
    client.post(f'/{conversation.slug}/v', data={'code': code})

    with client.session_transaction() as sess:
        xid = sess.get('xid')
    assert xid is not None

    p = Participant.query.filter_by(xid=xid).first()
    assert p is not None
    assert p.account_kind == ACCOUNT_KIND_VOUCHER
    assert p.conversation_id == conversation.id
    assert p.mw_user_id is None
    assert p.mw_username is None


# ── Access provider ───────────────────────────────────────────────────────────

def test_voucher_account_admitted_for_its_own_process(app, conversation):
    code = 'X7F3K9M2ABCD'
    _make_voucher(conversation, code=code)

    batch = VoucherBatch.query.filter_by(conversation_id=conversation.id).first()
    voucher = VoucherCode.query.filter_by(batch_id=batch.id).first()
    participant = Participant(
        mw_user_id=None, mw_username=None,
        account_kind=ACCOUNT_KIND_VOUCHER,
        conversation_id=conversation.id,
        xid='v' * 64,
    )
    db.session.add(participant)
    db.session.flush()
    voucher.participant_id = participant.id
    db.session.commit()

    conversation.gated = True
    conversation.gating_type = 'voucher'
    db.session.commit()

    decision = check_access(conversation, participant)
    assert decision.allowed is True


def test_voucher_account_refused_on_other_process(app, conversation):
    participant = Participant(
        mw_user_id=None, mw_username=None,
        account_kind=ACCOUNT_KIND_VOUCHER,
        conversation_id=conversation.id,
        xid='v' * 64,
    )
    db.session.add(participant)
    db.session.commit()

    conv2 = Conversation(
        slug='other-conv', polis_id='xyz9876543',
        title='Other', active=True, gated=True, gating_type='voucher',
    )
    db.session.add(conv2)
    db.session.commit()

    decision = check_access(conv2, participant)
    assert decision.allowed is False
    assert decision.reason == 'access-voucher-required'


def test_voucher_account_refused_when_revoked(app, conversation):
    code = 'X7F3K9M2ABCD'
    _make_voucher(conversation, code=code)
    batch = VoucherBatch.query.filter_by(conversation_id=conversation.id).first()
    voucher = VoucherCode.query.filter_by(batch_id=batch.id).first()

    participant = Participant(
        mw_user_id=None, mw_username=None,
        account_kind=ACCOUNT_KIND_VOUCHER,
        conversation_id=conversation.id,
        xid='w' * 64,
    )
    db.session.add(participant)
    db.session.flush()

    voucher.participant_id = participant.id
    voucher.status = 'revoked'
    db.session.commit()

    conversation.gated = True
    conversation.gating_type = 'voucher'
    db.session.commit()

    decision = check_access(conversation, participant)
    assert decision.allowed is False
    assert decision.reason == 'access-voucher-revoked'


def test_wikimedia_account_refused_on_voucher_process(app, conversation, participant):
    conversation.gated = True
    conversation.gating_type = 'voucher'
    db.session.commit()

    decision = check_access(conversation, participant)
    assert decision.allowed is False
    assert decision.reason == 'access-voucher-required'


def test_same_raw_code_in_two_processes_is_independent(app, conversation):
    """Two processes can use the same code string without collision."""
    code = 'X7F3K9M2ABCD'
    _make_voucher(conversation, code=code)

    conv2 = Conversation(
        slug='process-two', polis_id='def4567890',
        title='Second Process', active=True,
    )
    db.session.add(conv2)
    db.session.commit()

    _make_voucher(conv2, code=code)

    v1 = lookup_voucher(code, conversation.id)
    v2 = lookup_voucher(code, conv2.id)
    assert v1 is not None
    assert v2 is not None
    assert v1.id != v2.id
    assert v1.code_hmac != v2.code_hmac


# ── Referrer policy ───────────────────────────────────────────────────────────

def test_other_pages_use_strict_origin_referrer(client):
    resp = client.get('/')
    assert 'strict-origin-when-cross-origin' in resp.headers.get(
        'Referrer-Policy', '')


# ── Log redaction ─────────────────────────────────────────────────────────────

def test_voucher_query_param_is_redacted_in_url():
    from logging_setup import _redact
    redacted = _redact('GET /demo/v?v=X7F3K9M2ABCD HTTP/1.1')
    assert 'X7F3K9M2ABCD' not in redacted
    assert 'v=[redacted]' in redacted


def test_voucher_path_segment_is_redacted():
    from logging_setup import _redact
    redacted = _redact('GET /v/X7F3K9M2ABCD HTTP/1.1')
    assert 'X7F3K9M2ABCD' not in redacted
    assert '/v/[redacted]' in redacted


# ── End-to-end: redemption → session → access ─────────────────────────────────

def test_voucher_redemption_and_access_flow(app, client, conversation):
    """A complete walk: generate batch, redeem, access check, resume, revoke."""
    conversation.gated = True
    conversation.gating_type = 'voucher'
    db.session.commit()

    # 1. Organiser generates a batch with two codes.
    batch = VoucherBatch(conversation_id=conversation.id, label='E2E Test')
    db.session.add(batch)
    db.session.commit()
    codes = generate_voucher_codes(batch, 2)

    # 2. Anonymous user visits the voucher page and gets the form.
    resp = client.get(f'/{conversation.slug}/v')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Voucher code' in html
    assert conversation.title in html

    # 3. User types a valid code — gets redirected to the process.
    resp = client.post(
        f'/{conversation.slug}/v',
        data={'code': codes[0]},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/{conversation.slug}'

    # 4. Session now carries a voucher identity.
    with client.session_transaction() as sess:
        xid = sess.get('xid')
    assert xid is not None

    participant = Participant.query.filter_by(xid=xid).first()
    assert participant is not None
    assert participant.account_kind == ACCOUNT_KIND_VOUCHER
    assert participant.conversation_id == conversation.id

    # 5. The access provider admits the voucher account.
    decision = check_access(conversation, participant)
    assert decision.allowed is True

    # 6. Redeeming the same code again resumes (same session details).
    resp = client.post(
        f'/{conversation.slug}/v',
        data={'code': codes[0]},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('xid') == xid  # same xid — no duplicate participant

    # 7. The second (unused) code produces a different participant.
    resp = client.post(
        f'/{conversation.slug}/v',
        data={'code': codes[1]},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        xid2 = sess.get('xid')
    assert xid2 != xid

    # 8. Revoke the first participant's voucher. Access is lost.
    voucher = VoucherCode.query.filter_by(participant_id=participant.id).first()
    revoke_voucher(voucher)
    db.session.commit()

    decision = check_access(conversation, participant)
    assert decision.allowed is False
    assert decision.reason == 'access-voucher-revoked'

    # 9. The revoked code can no longer resume — invalid response.
    resp = client.post(
        f'/{conversation.slug}/v',
        data={'code': codes[0]},
    )
    html = resp.data.decode()
    assert 'not valid' in html