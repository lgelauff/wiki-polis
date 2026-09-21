"""Voucher code generation, redemption, and access provider (#368)."""

import re
from datetime import datetime, timedelta, timezone

import pytest

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
from services.identity import create_voucher_participant
from services.vouchers import (
    classify_voucher,
    generate_voucher_code,
    generate_voucher_codes,
    has_excluded_letters,
    is_well_formed,
    lookup_voucher,
    normalize_code,
    redeem_voucher_code,
    revoke_voucher,
    voucher_code_hmac,
)

CODE = 'X7F3K9M2ABCD'


@pytest.fixture
def voucher_conv(conversation):
    conversation.gated = True
    conversation.gating_type = 'voucher'
    db.session.commit()
    return conversation


def _make_voucher(conversation, code=CODE, **kwargs):
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


def _voucher_account(conversation, xid='v' * 64):
    participant = create_voucher_participant(conversation_id=conversation.id, xid=xid)
    db.session.add(participant)
    db.session.commit()
    return participant


def _redeem(client, conversation, code=CODE, **form):
    return client.post(f'/c/{conversation.slug}/v', data={'code': code, **form})


def _session_xid(client):
    with client.session_transaction() as sess:
        return sess.get('xid')


def _voucher_participants():
    return Participant.query.filter_by(account_kind=ACCOUNT_KIND_VOUCHER).all()


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
    assert normalize_code('abc def-ghj') == 'ABCDEFGHJ'
    assert normalize_code('  X7F3-K9M2  ') == 'X7F3K9M2'


def test_normalize_is_case_insensitive():
    assert normalize_code('x7f3k9m2abcd') == CODE


def test_normalize_never_rewrites_letters():
    assert normalize_code('o0il') == 'O0IL'
    assert normalize_code('x7f3-k9m2-abcd') == normalize_code('X7F3 K9M2 ABCD')


def test_excluded_letters_are_detected_in_any_case():
    assert has_excluded_letters('x7f3 k9m2 abco')
    assert has_excluded_letters('ILOU')
    assert not has_excluded_letters(CODE)


def test_generated_codes_never_use_excluded_letters():
    assert not any(has_excluded_letters(generate_voucher_code()) for _ in range(500))


def test_well_formed_rejects_wrong_length_and_alphabet():
    assert is_well_formed('x7f3 k9m2 abcd')
    assert not is_well_formed('X7F3K9M2ABC')
    assert not is_well_formed('X7F3K9M2ABCU')  # U is not Crockford


# ── HMAC ──────────────────────────────────────────────────────────────────────

def test_hmac_is_scoped_by_conversation_id(app):
    assert voucher_code_hmac(CODE, 1) != voucher_code_hmac(CODE, 2)


def test_hmac_is_stable_for_same_input(app):
    assert voucher_code_hmac(CODE, 42) == voucher_code_hmac(CODE, 42)


def test_hmac_matches_a_hand_copied_code(app):
    assert voucher_code_hmac('x7f3-k9m2-abcd', 42) == voucher_code_hmac(CODE, 42)


# ── Batch generation ──────────────────────────────────────────────────────────

def test_generate_voucher_codes_persists_rows(app, conversation):
    batch = VoucherBatch(conversation_id=conversation.id, label='Test')
    db.session.add(batch)
    codes = generate_voucher_codes(batch, 5)
    db.session.commit()

    assert len(set(codes)) == 5
    rows = VoucherCode.query.filter_by(batch_id=batch.id).all()
    assert len(rows) == 5
    assert {row.status for row in rows} == {'unused'}
    assert all(lookup_voucher(code, conversation.id) is not None for code in codes)


# ── Lookup and classification ─────────────────────────────────────────────────

def test_lookup_finds_unused_voucher(app, conversation):
    v = _make_voucher(conversation)
    found = lookup_voucher(CODE, conversation.id)
    assert found is not None
    assert found.id == v.id


def test_lookup_returns_none_for_wrong_code(app, conversation):
    _make_voucher(conversation)
    assert lookup_voucher('ZZZZZZZZZZZZ', conversation.id) is None


def test_lookup_returns_none_for_wrong_conversation(app, conversation):
    _make_voucher(conversation)
    conv2 = Conversation(slug='other-conv', polis_id='xyz9876543', title='Other', active=True)
    db.session.add(conv2)
    db.session.commit()
    assert lookup_voucher(CODE, conv2.id) is None


def test_revoke_sets_status_and_timestamp(app, conversation):
    v = _make_voucher(conversation)
    revoke_voucher(v)
    db.session.commit()
    assert v.status == 'revoked'
    assert v.revoked_at is not None


def test_redeemed_code_whose_account_is_gone_cannot_mint_another(app, conversation):
    """participant_id is SET NULL on delete; the code must not fall back to 'unused'."""
    _make_voucher(conversation, status='redeemed', participant_id=None)
    assert classify_voucher(CODE, conversation.id).outcome == 'invalid'


def test_concurrent_first_use_creates_one_account(app, voucher_conv):
    """Both requests classify the code as unused; the second claim loses and
    resumes the winner's account instead of creating a second one."""
    _make_voucher(voucher_conv)
    first = classify_voucher(CODE, voucher_conv.id)
    second = classify_voucher(CODE, voucher_conv.id)
    assert first.outcome == second.outcome == 'redeem'

    def factory(xid):
        return lambda: create_voucher_participant(conversation_id=voucher_conv.id, xid=xid)

    winner = redeem_voucher_code(first.voucher, voucher_conv.id, factory('a' * 64))
    loser = redeem_voucher_code(second.voucher, voucher_conv.id, factory('b' * 64))

    assert winner is not None
    assert loser is not None and loser.id == winner.id
    assert len(_voucher_participants()) == 1


def test_expired_code_cannot_be_claimed(app, voucher_conv):
    voucher = _make_voucher(
        voucher_conv, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    created = redeem_voucher_code(
        voucher, voucher_conv.id,
        lambda: create_voucher_participant(conversation_id=voucher_conv.id, xid='a' * 64),
    )
    assert created is None
    assert _voucher_participants() == []


# ── Voucher entry endpoint ────────────────────────────────────────────────────

def test_voucher_page_renders_form_with_csrf_field(app, client, voucher_conv):
    resp = client.get(f'/c/{voucher_conv.slug}/v')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Voucher code' in html
    assert voucher_conv.title in html
    assert 'name="csrf_token"' in html
    assert resp.headers['Cache-Control'] == 'no-store'
    assert resp.headers['Referrer-Policy'] == 'no-referrer'


def test_voucher_page_renders_from_the_message_catalogue(app, client, voucher_conv):
    html = client.get(f'/c/{voucher_conv.slug}/v?uselang=qqx').data.decode()
    assert '(voucher-page-label)' in html
    assert '(voucher-page-intro)' in html
    assert f'(voucher-page-doc-title: {voucher_conv.title})' in html
    assert 'Voucher code' not in html


def test_short_voucher_url_is_the_same_page(app, client, voucher_conv):
    resp = client.get(f'/{voucher_conv.slug}/v')
    assert resp.status_code == 200
    assert 'name="code"' in resp.data.decode()


def test_voucher_page_is_404_on_a_conversation_without_voucher_gating(
    app, client, conversation,
):
    _make_voucher(conversation)
    assert client.get(f'/c/{conversation.slug}/v').status_code == 404
    assert client.get(f'/c/{conversation.slug}/v?v={CODE}').status_code == 404
    assert _voucher_participants() == []


def test_typed_code_redeems_with_csrf_enabled(app, client, voucher_conv):
    """The production config protects every POST; the form must carry the token."""
    _make_voucher(voucher_conv)
    app.config['WTF_CSRF_ENABLED'] = True
    page = client.get(f'/c/{voucher_conv.slug}/v').data.decode()
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)

    resp = _redeem(client, voucher_conv, csrf_token=token)

    assert resp.status_code == 302
    assert _session_xid(client) is not None


def test_post_without_csrf_token_is_refused_when_csrf_is_enabled(app, client, voucher_conv):
    _make_voucher(voucher_conv)
    app.config['WTF_CSRF_ENABLED'] = True
    assert _redeem(client, voucher_conv).status_code == 400
    assert _voucher_participants() == []


def test_redemption_redirects_to_the_conversation_page(app, client, voucher_conv):
    _make_voucher(voucher_conv)
    resp = _redeem(client, voucher_conv)
    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/c/{voucher_conv.slug}'
    assert CODE not in resp.headers['Location']


def test_linked_code_redeems_and_leaves_the_address(app, client, voucher_conv):
    _make_voucher(voucher_conv)
    resp = client.get(f'/{voucher_conv.slug}/v?v={CODE.lower()}')
    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/c/{voucher_conv.slug}'
    assert _session_xid(client) is not None


def test_code_with_excluded_letters_gets_its_own_message(app, client, voucher_conv):
    """A misread 0 or 1 is pointed out rather than silently corrected."""
    _make_voucher(voucher_conv, code='0011ABCDEFGH')
    resp = _redeem(client, voucher_conv, code='OO1l-abcd-efgh')
    html = resp.data.decode()
    assert resp.status_code == 200
    assert 'never use the letters I, L, O or U' in html
    assert 'value="OO1l-abcd-efgh"' in html  # kept in the field to correct
    assert 'aria-invalid="true"' in html
    assert _voucher_participants() == []


@pytest.mark.parametrize('kwargs', [
    {'status': 'revoked'},
    {'expires_at': datetime.now(timezone.utc) - timedelta(days=1)},
    {'status': 'reserved', 'reserved_until': datetime.now(timezone.utc) + timedelta(minutes=5)},
])
def test_unusable_codes_get_the_same_answer_as_a_wrong_code(app, client, voucher_conv, kwargs):
    _make_voucher(voucher_conv, **kwargs)
    wrong = _redeem(client, voucher_conv, code='ZZZZZZZZZZZZ').data.decode()
    unusable = _redeem(client, voucher_conv).data.decode()
    assert 'not valid' in unusable
    assert unusable == wrong
    assert CODE not in unusable
    assert _voucher_participants() == []


def test_empty_and_malformed_codes_show_field_errors(app, client, voucher_conv):
    empty = _redeem(client, voucher_conv, code='').data.decode()
    assert 'Enter a voucher code' in empty
    assert 'aria-invalid="true"' in empty
    assert 'aria-describedby="code-hint code-error"' in empty
    malformed = _redeem(client, voucher_conv, code='ABC').data.decode()
    assert '12 letters and numbers' in malformed


def test_voucher_account_is_conversation_scoped(app, client, voucher_conv):
    _make_voucher(voucher_conv)
    _redeem(client, voucher_conv)

    p = Participant.query.filter_by(xid=_session_xid(client)).first()
    assert p.account_kind == ACCOUNT_KIND_VOUCHER
    assert p.conversation_id == voucher_conv.id
    assert p.mw_user_id is None
    assert p.mw_username is None


def test_the_code_resumes_the_same_account_in_another_browser(app, voucher_conv):
    """#412: the code joins once and authenticates that account thereafter."""
    _make_voucher(voucher_conv)
    first, second = app.test_client(), app.test_client()
    _redeem(first, voucher_conv)
    _redeem(second, voucher_conv)
    assert _session_xid(first) == _session_xid(second)
    assert len(_voucher_participants()) == 1


def test_expiry_does_not_end_an_account_that_already_redeemed(app, client, voucher_conv):
    voucher = _make_voucher(voucher_conv)
    _redeem(client, voucher_conv)
    xid = _session_xid(client)
    voucher.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.session.commit()

    other = app.test_client()
    assert _redeem(other, voucher_conv).status_code == 302
    assert _session_xid(other) == xid


# ── Session identity ──────────────────────────────────────────────────────────

def test_wikimedia_session_is_asked_before_it_is_replaced(app, client, voucher_conv, participant):
    _make_voucher(voucher_conv)
    with client.session_transaction() as sess:
        sess['username'] = 'testuser'
        sess['xid'] = participant.xid

    # A link must not silently swap the identity.
    resp = client.get(f'/c/{voucher_conv.slug}/v?v={CODE}')
    assert resp.status_code == 200
    assert 'signed in with another account' in resp.data.decode()
    assert _session_xid(client) == participant.xid
    assert _voucher_participants() == []

    resp = _redeem(client, voucher_conv, confirm='1')
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert 'username' not in sess
        voucher_xid = sess['xid']
    assert voucher_xid != participant.xid


def test_voucher_session_carries_nothing_from_the_previous_one(app, client, voucher_conv):
    _make_voucher(voucher_conv)
    with client.session_transaction() as sess:
        sess['demo_conversation_id'] = 99
        sess['particiapi_api_sessions'] = {str(voucher_conv.id): 'someone-else'}
        sess['space'] = 'demo'
    _redeem(client, voucher_conv)
    with client.session_transaction() as sess:
        assert set(sess.keys()) - {'_permanent', '_fresh', 'csrf_token'} == {'xid', 'emailable'}


def test_second_code_in_the_same_session_is_refused_and_stays_unused(app, client, voucher_conv):
    _make_voucher(voucher_conv)
    second = _make_voucher(voucher_conv, code='ABCDEFGHJKMN')
    _redeem(client, voucher_conv)
    xid = _session_xid(client)

    resp = _redeem(client, voucher_conv, code='ABCDEFGHJKMN', confirm='1')

    assert 'already take part' in resp.data.decode()
    assert _session_xid(client) == xid
    db.session.refresh(second)
    assert second.status == 'unused'


def test_reopening_your_own_code_keeps_the_session(app, client, voucher_conv):
    _make_voucher(voucher_conv)
    _redeem(client, voucher_conv)
    xid = _session_xid(client)
    resp = client.get(f'/c/{voucher_conv.slug}/v?v={CODE}')
    assert resp.status_code == 302
    assert _session_xid(client) == xid


# ── Access provider ───────────────────────────────────────────────────────────

def test_redeemed_voucher_account_is_admitted(app, voucher_conv):
    voucher = _make_voucher(voucher_conv)
    participant = _voucher_account(voucher_conv)
    voucher.participant_id = participant.id
    voucher.status = 'redeemed'
    db.session.commit()

    assert check_access(voucher_conv, participant).allowed is True


def test_voucher_account_without_a_redeemed_code_is_refused(app, voucher_conv):
    """Fail closed: being a voucher account scoped here is not enough."""
    participant = _voucher_account(voucher_conv)
    decision = check_access(voucher_conv, participant)
    assert decision.allowed is False
    assert decision.reason == 'access-voucher-needed'


def test_voucher_account_is_refused_once_its_batch_is_deleted(app, voucher_conv):
    voucher = _make_voucher(voucher_conv)
    participant = _voucher_account(voucher_conv)
    voucher.participant_id = participant.id
    voucher.status = 'redeemed'
    db.session.commit()
    db.session.delete(voucher.batch)
    db.session.commit()

    assert check_access(voucher_conv, participant).allowed is False


def test_voucher_account_refused_when_revoked(app, voucher_conv):
    voucher = _make_voucher(voucher_conv)
    participant = _voucher_account(voucher_conv, xid='w' * 64)
    voucher.participant_id = participant.id
    voucher.status = 'revoked'
    db.session.commit()

    decision = check_access(voucher_conv, participant)
    assert decision.allowed is False
    assert decision.reason == 'access-voucher-revoked'


def test_revoked_participant_is_in_access_lost(app, voucher_conv):
    voucher = _make_voucher(voucher_conv)
    participant = _voucher_account(voucher_conv)
    voucher.participant_id = participant.id
    voucher.status = 'revoked'
    db.session.add(Participation(
        participant_id=participant.id, conversation_id=voucher_conv.id,
        pseudonym='quiet-otter',
    ))
    db.session.commit()

    assert check_access(voucher_conv, participant).viewer == 'access_lost'


@pytest.mark.parametrize('other', [
    {'gated': True, 'gating_type': 'voucher'},
    {'gated': False, 'gating_type': None},
    {'gated': True, 'gating_type': 'invite_only'},
])
def test_voucher_account_refused_on_every_other_process(app, conversation, other):
    participant = _voucher_account(conversation)
    conv2 = Conversation(
        slug='other-conv', polis_id='xyz9876543', title='Other', active=True, **other,
    )
    db.session.add(conv2)
    db.session.commit()

    decision = check_access(conv2, participant)
    assert decision.allowed is False
    assert decision.reason == 'access-voucher-other'


def test_wikimedia_account_refused_on_voucher_process(app, voucher_conv, participant):
    decision = check_access(voucher_conv, participant)
    assert decision.allowed is False
    assert decision.reason == 'access-voucher-needed'


def test_same_raw_code_in_two_processes_is_independent(app, conversation):
    """Two processes can use the same code string without collision."""
    _make_voucher(conversation)
    conv2 = Conversation(slug='process-two', polis_id='def4567890', title='Second Process', active=True)
    db.session.add(conv2)
    db.session.commit()
    _make_voucher(conv2)

    v1 = lookup_voucher(CODE, conversation.id)
    v2 = lookup_voucher(CODE, conv2.id)
    assert v1.id != v2.id
    assert v1.code_hmac != v2.code_hmac


# ── Referrer policy ───────────────────────────────────────────────────────────

def test_other_pages_use_strict_origin_referrer(client):
    resp = client.get('/')
    assert 'strict-origin-when-cross-origin' in resp.headers.get('Referrer-Policy', '')


# ── Log redaction ─────────────────────────────────────────────────────────────

def test_voucher_query_param_is_redacted_in_url():
    from logging_setup import _redact
    redacted = _redact(f'GET /c/demo/v?v={CODE} HTTP/1.1')
    assert CODE not in redacted
    assert 'v=[redacted]' in redacted


def test_voucher_path_segment_is_redacted():
    from logging_setup import _redact
    redacted = _redact(f'GET /v/{CODE} HTTP/1.1')
    assert CODE not in redacted
    assert '/v/[redacted]' in redacted


# ── End-to-end: redemption → session → API → revoke ──────────────────────────

def test_voucher_redemption_and_access_flow(app, client, voucher_conv):
    batch = VoucherBatch(conversation_id=voucher_conv.id, label='E2E Test')
    db.session.add(batch)
    codes = generate_voucher_codes(batch, 2)
    db.session.commit()

    # Logged out: the workspace refuses and says this is a voucher process.
    refused = client.get(f'/api/v1/conversations/{voucher_conv.slug}/workspace')
    assert refused.status_code == 403
    assert refused.get_json()['error']['details']['gatingType'] == 'voucher'

    # Typing a code redeems it and lands on the conversation page.
    resp = client.post(f'/c/{voucher_conv.slug}/v', data={'code': codes[0]})
    assert resp.headers['Location'] == f'/c/{voucher_conv.slug}'

    # The SPA sees a signed-in voucher session, and the workspace admits it.
    session_state = client.get('/api/v1/session').get_json()['data']
    assert session_state['state'] == 'voucher'
    assert session_state['user'] is None
    assert session_state['capabilities']['administerSite'] is False
    workspace = client.get(f'/api/v1/conversations/{voucher_conv.slug}/workspace')
    assert workspace.status_code == 200, workspace.get_data(as_text=True)

    # Joining works and never opts a voucher account into talk-page notices.
    joined = client.post(
        f'/api/v1/conversations/{voucher_conv.slug}/participation',
        json={'pseudonym': 'quiet-otter', 'notifyEmail': True, 'notifyTalkPage': True},
    )
    assert joined.status_code == 201, joined.get_data(as_text=True)
    assert joined.get_json()['data']['notifications'] == {'email': False, 'talkPage': False}

    participant = Participant.query.filter_by(xid=_session_xid(client)).first()

    # Revoking the code puts the account in "joined, access lost".
    voucher = VoucherCode.query.filter_by(participant_id=participant.id).first()
    revoke_voucher(voucher)
    db.session.commit()
    lost = client.get(f'/api/v1/conversations/{voucher_conv.slug}/workspace')
    assert lost.status_code == 403
    details = lost.get_json()['error']['details']
    assert details['viewer'] == 'access_lost'
    assert details['reason'] == 'access-voucher-revoked'

    # The revoked code no longer opens anything.
    assert 'not valid' in client.post(
        f'/c/{voucher_conv.slug}/v', data={'code': codes[0]},
    ).data.decode()
