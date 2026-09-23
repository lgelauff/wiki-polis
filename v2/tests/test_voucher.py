"""Voucher code generation, redemption, and access provider (#368)."""

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import g

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
    import_voucher_codes,
    lookup_voucher,
    normalize_code,
    redeem_voucher_code,
    revoke_voucher,
    voucher_code_hmac,
)

# Any time before the suite runs, and any time after it: the unusable-code cases below
# care about which side of now a date falls, never about how far.
_LONG_PAST = datetime(2020, 1, 1, tzinfo=timezone.utc)
_LONG_FUTURE = datetime(2099, 1, 1, tzinfo=timezone.utc)

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


# ── Import ────────────────────────────────────────────────────────────────────

def _batch(conversation):
    batch = VoucherBatch(conversation_id=conversation.id)
    db.session.add(batch)
    db.session.flush()
    return batch


def test_codes_for_an_unflushed_batch_hash_with_its_conversation(app, conversation):
    """A batch built with conversation= has no conversation_id until flushed; the
    HMAC must still be scoped to the conversation, not to None."""
    batch = VoucherBatch(conversation=conversation)
    db.session.add(batch)
    codes = generate_voucher_codes(batch, 1)
    import_voucher_codes(batch, ['ROOM-101'])
    db.session.commit()
    assert lookup_voucher(codes[0], conversation.id) is not None
    assert lookup_voucher('ROOM101', conversation.id) is not None


def test_import_normalises_and_skips_blank_lines(app, conversation):
    result = import_voucher_codes(_batch(conversation), ['wiki-ola-01\n', '\n', '  Smith 2024 \n'])
    db.session.commit()

    assert result.added == ['WIKIOLA01', 'SMITH2024']
    # Stored codes are found however they are typed, excluded letters included.
    assert lookup_voucher('Wiki Ola 01', conversation.id) is not None
    assert lookup_voucher('smith-2024', conversation.id) is not None


def test_import_reports_duplicates_and_rejects(app, conversation):
    _make_voucher(conversation, code='EXISTING1')
    result = import_voucher_codes(_batch(conversation), [
        'ABCDE',        # five characters is the floor
        'abc-de',       # same code as the line above once normalised
        'existing-1',   # already in this conversation
        'ABCD',         # too short
        'café-2024',    # not ASCII letters and digits
        'A' * 65,       # too long
    ])
    assert result.added == ['ABCDE']
    assert result.duplicates == ['ABCDE', 'EXISTING1']
    assert result.rejected == ['ABCD', 'CAFÉ2024', 'A' * 65]


def test_the_same_imported_list_works_in_two_processes(app, client, voucher_conv):
    """Organizers keep one list of codes across processes; each process gets its
    own rows, and each code makes a separate account per process."""
    conv2 = Conversation(
        slug='process-two', polis_id='def4567890', title='Second Process', active=True,
        gated=True, gating_type='voucher',
    )
    db.session.add(conv2)
    db.session.commit()
    for conv in (voucher_conv, conv2):
        assert import_voucher_codes(_batch(conv), ['ROOM-101']).added == ['ROOM101']
    db.session.commit()

    _redeem(client, voucher_conv, code='room 101')
    first = _session_xid(client)
    other = app.test_client()
    _redeem(other, conv2, code='room 101')

    assert first and _session_xid(other) and first != _session_xid(other)
    assert len(_voucher_participants()) == 2


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
    assert resp.headers['Referrer-Policy'] == 'strict-origin'


def test_voucher_page_renders_from_the_message_catalogue(app, client, voucher_conv):
    html = client.get(f'/c/{voucher_conv.slug}/v?uselang=qqx').data.decode()
    assert '(voucher-page-label)' in html
    assert '(voucher-page-intro)' in html
    assert f'(voucher-page-doc-title: {voucher_conv.title})' in html
    assert 'Voucher code' not in html


def test_there_is_no_top_level_voucher_url(app, client, voucher_conv):
    """Conversations live under /c/; /<slug>/v is not a second door."""
    _make_voucher(voucher_conv)
    assert client.get(f'/{voucher_conv.slug}/v').status_code == 404
    assert client.get(f'/{voucher_conv.slug}/v?v={CODE}').status_code == 404
    assert _voucher_participants() == []


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


def _https_form(app, conv):
    """A fresh HTTPS browser on the entry page: (client, csrf token)."""
    # The test app keeps one app context, so Flask-WTF's per-request token cache
    # in g would otherwise hand this browser the previous browser's token.
    g.pop('csrf_token', None)
    client = app.test_client()
    page = client.get(f'/c/{conv.slug}/v', base_url='https://localhost')
    assert page.headers['Referrer-Policy'] == 'strict-origin'
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.data.decode()).group(1)
    return client, token


def test_https_form_post_needs_the_referer_the_page_policy_allows(app, voucher_conv):
    """Over HTTPS Flask-WTF refuses a POST without a Referer, so the page's referrer
    policy must let the browser send one (staging: "The referrer header is
    missing" under no-referrer). Each POST uses its own fresh session, so the
    refusal can only come from the Referer check."""
    _make_voucher(voucher_conv)
    app.config['WTF_CSRF_ENABLED'] = True
    url = f'/c/{voucher_conv.slug}/v'

    client, token = _https_form(app, voucher_conv)
    refused = client.post(url, base_url='https://localhost',
                          data={'code': CODE, 'csrf_token': token})
    assert refused.status_code == 400
    assert b'referrer header is missing' in refused.data

    # Under strict-origin the browser sends just the origin, which is enough.
    client, token = _https_form(app, voucher_conv)
    accepted = client.post(url, base_url='https://localhost',
                           data={'code': CODE, 'csrf_token': token},
                           headers={'Referer': 'https://localhost/'})
    assert accepted.status_code == 302, accepted.data[-300:]


def test_forms_post_back_without_the_code_in_the_address(app, client, voucher_conv):
    """A page reached with ?v=<code> posts to the bare entry path, so the code
    never rides along as the form post's Referer."""
    html = client.get(f'/c/{voucher_conv.slug}/v?v=WRONG-9999').data.decode()
    assert f'action="/c/{voucher_conv.slug}/v"' in html


def test_too_short_input_says_so_and_keeps_what_was_typed(app, client, voucher_conv):
    html = _redeem(client, voucher_conv, code='ab-c').data.decode()
    assert 'at least 5 characters' in html
    assert 'value="ab-c"' in html
    assert 'not valid' not in html


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
    resp = client.get(f'/c/{voucher_conv.slug}/v?v={CODE.lower()}')
    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/c/{voucher_conv.slug}'
    assert _session_xid(client) is not None


def test_code_on_the_conversation_link_redeems(app, client, voucher_conv):
    """/c/<slug>?v=<code> is handed to the entry route, which redeems and lands
    on the plain conversation page."""
    _make_voucher(voucher_conv)
    first = client.get(f'/c/{voucher_conv.slug}?v={CODE}')
    assert first.status_code == 302
    assert first.headers['Location'] == f'/c/{voucher_conv.slug}/v?v={CODE}'
    assert first.headers['Referrer-Policy'] == 'strict-origin'

    landed = client.get(first.headers['Location'])
    assert landed.headers['Location'] == f'/c/{voucher_conv.slug}'
    assert _session_xid(client) is not None


def test_code_on_a_conversation_without_vouchers_is_dropped(app, client, conversation):
    resp = client.get(f'/c/{conversation.slug}?v={CODE}')
    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/c/{conversation.slug}'
    assert _voucher_participants() == []


def test_missed_code_with_excluded_letters_gets_a_hint(app, client, voucher_conv):
    """A misread 0 or 1 is pointed out rather than silently corrected."""
    _make_voucher(voucher_conv, code='0011ABCDEFGH')
    resp = _redeem(client, voucher_conv, code='OO1l-abcd-efgh')
    html = resp.data.decode()
    assert resp.status_code == 200
    assert 'check whether those should be the numbers 1 and 0' in html
    assert 'value="OO1l-abcd-efgh"' in html  # kept in the field to correct
    assert 'aria-invalid="true"' in html
    assert _voucher_participants() == []


def test_imported_code_with_excluded_letters_redeems(app, client, voucher_conv):
    """Organizers' own codes may contain I, L, O or U; entry must not refuse them."""
    import_voucher_codes(_batch(voucher_conv), ['OLIU-2024'])
    db.session.commit()
    assert _redeem(client, voucher_conv, code='oliu 2024').status_code == 302


def test_short_imported_code_redeems(app, client, voucher_conv):
    import_voucher_codes(_batch(voucher_conv), ['K7Q2M'])
    db.session.commit()
    assert _redeem(client, voucher_conv, code='k7q2m').status_code == 302


# Sentinel dates, not offsets from now: the cases only need "already over" and "not over
# yet", and a date cannot be overtaken by a slow suite. A reservation five minutes ahead,
# computed when this file was imported, could be: a run that took longer than that to reach
# this test found it expired, and an expired reservation is claimable
# (services/vouchers.py:225), so the code redeemed instead of being refused.
@pytest.mark.parametrize('unusable', [
    pytest.param({'status': 'revoked'}, id='revoked'),
    pytest.param({'expires_at': _LONG_PAST}, id='expired'),
    pytest.param({'status': 'reserved', 'reserved_until': _LONG_FUTURE}, id='reserved'),
])
@pytest.mark.parametrize('code,wrong_code', [
    (CODE, 'ZZZZZZZZZZZZ'),
    ('OLIU2024', 'OLIU2025'),  # the excluded-letter hint depends on the input only
])
def test_unusable_codes_get_the_same_answer_as_a_wrong_code(
    app, client, voucher_conv, unusable, code, wrong_code,
):
    _make_voucher(voucher_conv, code=code, **unusable)
    wrong = _redeem(client, voucher_conv, code=wrong_code).data.decode()
    refused = _redeem(client, voucher_conv, code=code).data.decode()
    assert 'not valid' in refused
    assert refused.replace(code, wrong_code) == wrong
    assert _voucher_participants() == []


def test_empty_code_shows_a_field_error(app, client, voucher_conv):
    empty = _redeem(client, voucher_conv, code='').data.decode()
    assert 'Enter a voucher code' in empty
    assert 'aria-invalid="true"' in empty
    assert 'aria-describedby="code-hint code-error"' in empty


def test_a_missed_code_is_not_echoed_back(app, client, voucher_conv):
    html = _redeem(client, voucher_conv, code='ZZZZZZZZZZZZ').data.decode()
    assert 'not valid' in html
    assert 'ZZZZZZZZZZZZ' not in html


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_cli_generates_codes_that_redeem(app, client, voucher_conv):
    result = app.test_cli_runner().invoke(
        args=['vouchers', 'generate', voucher_conv.slug, '3', '--label', 'Workshop'],
    )
    assert result.exit_code == 0, result.output
    codes = result.output.split('\n')[:3]
    assert all(re.fullmatch(r'[0-9A-Z]{4} [0-9A-Z]{4} [0-9A-Z]{4}', c) for c in codes)
    assert VoucherBatch.query.filter_by(label='Workshop').one().conversation_id == voucher_conv.id
    assert _redeem(client, voucher_conv, code=codes[0]).status_code == 302


def test_cli_imports_codes_and_reports_skips(app, voucher_conv, tmp_path):
    source = tmp_path / 'codes.txt'
    source.write_text('ROOM-101\nroom101\nAB\n', encoding='utf-8')
    result = app.test_cli_runner().invoke(
        args=['vouchers', 'import', voucher_conv.slug, str(source)],
    )
    assert result.exit_code == 0, result.output
    assert 'Imported 1 codes.' in result.output
    assert 'Skipped 1 duplicates.' in result.output
    assert '  AB' in result.output
    assert lookup_voucher('room 101', voucher_conv.id) is not None


def test_cli_import_warns_about_weak_codes_without_printing_them(app, voucher_conv, tmp_path):
    source = tmp_path / 'codes.txt'
    source.write_text('12345\n67890\nK7Q2M-X9Z\nROOMCODE-2024\n', encoding='utf-8')
    result = app.test_cli_runner().invoke(
        args=['vouchers', 'import', voucher_conv.slug, str(source)],
    )
    assert result.exit_code == 0, result.output
    assert 'Imported 4 codes.' in result.output
    assert 'Warning: 2 of these codes are digits only or shorter than 8' in result.output
    assert '12345' not in result.output


def test_cli_refuses_an_unknown_conversation(app, tmp_path):
    result = app.test_cli_runner().invoke(args=['vouchers', 'generate', 'no-such-slug', '1'])
    assert result.exit_code != 0
    assert 'No conversation' in result.output


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


def test_voucher_account_joins_without_the_wikimedia_eligibility_check(
    app, client, voucher_conv,
):
    """The #146 eligibility gate checks a Wikimedia username; a voucher account has
    none, and holding the voucher is its admission (staging: eligibility_unavailable)."""
    voucher_conv.eligibility_event_id = 'some-canivote-policy'
    db.session.commit()
    _make_voucher(voucher_conv)
    _redeem(client, voucher_conv)

    with patch('app.requests.get') as upstream:
        joined = client.post(
            f'/api/v1/conversations/{voucher_conv.slug}/participation',
            json={'pseudonym': 'quiet-otter'},
        )
    assert joined.status_code == 201, joined.get_data(as_text=True)
    assert joined.get_json()['data']['eligibilityStatus'] == 'not_required'
    upstream.assert_not_called()
    participation = Participation.query.filter_by(conversation_id=voucher_conv.id).one()
    assert participation.eligibility_detail == {'reason': 'voucher admission'}


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
