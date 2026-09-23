"""Failed-attempt budgets on voucher entry (#368).

Run with the limiter ON (see test_api_rate_limits). Only misses spend a budget:
a room entering valid codes never trips it, while guessing does, both from one
browser session and spread across many. Nothing is locked or invalidated.
"""
import logging

import pytest

from app import (_VOUCHER_PROCESS_FAILURE_LIMIT, _VOUCHER_SESSION_FAILURE_LIMIT,
                 limiter)
from db import Conversation, VoucherBatch, VoucherCode, db
from services.vouchers import import_voucher_codes
from tests.test_api_rate_limits import limited_app  # noqa: F401  (fixture)

SESSION_BUDGET = int(_VOUCHER_SESSION_FAILURE_LIMIT.split()[0])
PROCESS_BUDGET = int(_VOUCHER_PROCESS_FAILURE_LIMIT.split()[0])
CODE = 'ROOM-2024'


def _process(slug='room'):
    conv = Conversation(
        slug=slug, polis_id=f'{slug}123456', title=f'Process {slug}', active=True,
        gated=True, gating_type='voucher',
    )
    db.session.add(conv)
    db.session.flush()
    batch = VoucherBatch(conversation_id=conv.id)
    db.session.add(batch)
    import_voucher_codes(batch, [CODE, 'SPARE-001'])
    db.session.commit()
    return conv


def _try(client, conv, code):
    return client.post(f'/c/{conv.slug}/v', data={'code': code})


@pytest.fixture
def conv(limited_app):  # noqa: F811
    limiter.reset()
    return _process()


def test_a_session_is_throttled_after_its_budget_of_misses(limited_app, conv):  # noqa: F811
    client = limited_app.test_client()
    statuses = [_try(client, conv, f'WRONG{i:04d}').status_code for i in range(SESSION_BUDGET)]
    assert statuses == [200] * SESSION_BUDGET

    breach = _try(client, conv, 'WRONG9999')
    assert breach.status_code == 429
    assert 0 < int(breach.headers['Retry-After']) <= 60
    assert 'Too many codes were tried here' in breach.data.decode()
    assert breach.headers['Cache-Control'] == 'no-store'

    # While throttled even a valid code waits, but it is not spent or locked.
    assert _try(client, conv, CODE).status_code == 429
    assert {v.status for v in VoucherCode.query.all()} == {'unused'}


def test_valid_codes_and_resumes_never_spend_the_budget(limited_app, conv):  # noqa: F811
    client = limited_app.test_client()
    for _ in range(SESSION_BUDGET * 2):
        assert _try(client, conv, CODE).status_code == 302


def test_empty_submissions_are_not_counted_as_guesses(limited_app, conv):  # noqa: F811
    client = limited_app.test_client()
    for _ in range(SESSION_BUDGET + 1):
        assert _try(client, conv, '').status_code == 200


def test_the_process_budget_catches_guessing_spread_over_sessions(
    limited_app, conv, caplog,  # noqa: F811
):
    """A fresh session per guess escapes the session budget, not the process one."""
    for i in range(PROCESS_BUDGET):
        assert _try(limited_app.test_client(), conv, f'GUESS{i:04d}').status_code == 200

    with caplog.at_level(logging.WARNING):
        breach = _try(limited_app.test_client(), conv, 'GUESS9999')
    assert breach.status_code == 429
    assert f'conversation {conv.id} exhausted' in caplog.text
    assert 'GUESS' not in caplog.text


def test_each_process_has_its_own_budget(limited_app, conv):  # noqa: F811
    other = _process('other-room')
    for i in range(PROCESS_BUDGET):
        _try(limited_app.test_client(), conv, f'GUESS{i:04d}')
    assert _try(limited_app.test_client(), conv, 'GUESS9999').status_code == 429

    assert _try(limited_app.test_client(), other, CODE).status_code == 302


def test_a_valid_code_redeems_once_the_window_has_passed(limited_app, conv):  # noqa: F811
    client = limited_app.test_client()
    for i in range(SESSION_BUDGET + 1):
        _try(client, conv, f'WRONG{i:04d}')
    assert _try(client, conv, CODE).status_code == 429

    limiter.reset()  # the window passing, without sleeping a minute

    assert _try(client, conv, CODE).status_code == 302


def _get(client, conv, code):
    return client.get(f'/c/{conv.slug}/v?v={code}')


def test_wrong_codes_in_links_count_too(limited_app, conv):  # noqa: F811
    client = limited_app.test_client()
    for i in range(SESSION_BUDGET):
        assert _get(client, conv, f'WRONG{i:04d}').status_code == 200
    assert _get(client, conv, 'WRONG9999').status_code == 429


def test_repeated_valid_links_are_never_throttled(limited_app, conv):  # noqa: F811
    for _ in range(SESSION_BUDGET * 2):
        assert _get(limited_app.test_client(), conv, CODE).status_code == 302


def test_the_blank_form_and_what_was_typed_survive_throttling(limited_app, conv):  # noqa: F811
    client = limited_app.test_client()
    for i in range(SESSION_BUDGET):
        _try(client, conv, f'WRONG{i:04d}')
    breach = _try(client, conv, 'ROOM-2O24')
    assert breach.status_code == 429
    assert 'value="ROOM-2O24"' in breach.data.decode()  # to send again later
    assert client.get(f'/c/{conv.slug}/v').status_code == 200  # blank form


def test_unknown_slugs_and_short_inputs_are_not_charged(limited_app, conv):  # noqa: F811
    client = limited_app.test_client()
    for i in range(PROCESS_BUDGET + 10):
        assert client.post('/c/no-such-process/v', data={'code': f'WRONG{i:04d}'}).status_code == 404
    for _ in range(SESSION_BUDGET + 1):
        assert _try(client, conv, 'AB-C').status_code == 200
    assert _try(client, conv, 'WRONG0001').status_code == 200


def test_a_post_refused_by_csrf_is_not_charged(limited_app, conv):  # noqa: F811
    limited_app.config['WTF_CSRF_ENABLED'] = True
    client = limited_app.test_client()
    for i in range(SESSION_BUDGET + 1):
        assert _try(client, conv, f'WRONG{i:04d}').status_code == 400
    limited_app.config['WTF_CSRF_ENABLED'] = False
    assert _try(client, conv, 'WRONG0001').status_code == 200


def test_the_session_budget_is_per_process(limited_app, conv):  # noqa: F811
    other = _process('other-room')
    client = limited_app.test_client()
    for i in range(SESSION_BUDGET + 1):
        _try(client, conv, f'WRONG{i:04d}')
    assert _try(client, conv, 'WRONG9999').status_code == 429
    assert _try(client, other, 'WRONG9999').status_code == 200


def test_checking_codes_through_the_switch_page_is_charged(limited_app, conv):  # noqa: F811
    """A signed-in browser gets the switch page for a valid code without using it;
    that reveals validity, so it spends the budget like a miss."""
    from db import Participant
    wiki = Participant(mw_user_id=4242, mw_username='Someone', xid='w' * 64)
    db.session.add(wiki)
    db.session.commit()
    client = limited_app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'Someone'
        sess['xid'] = wiki.xid
    for _ in range(SESSION_BUDGET):
        assert 'signed in with another account' in _try(client, conv, CODE).data.decode()
    assert _try(client, conv, CODE).status_code == 429


def test_the_exhausted_warning_is_logged_once_per_window(limited_app, conv, caplog):  # noqa: F811
    for i in range(PROCESS_BUDGET):
        _try(limited_app.test_client(), conv, f'GUESS{i:04d}')
    with caplog.at_level(logging.WARNING):
        for i in range(5):
            assert _try(limited_app.test_client(), conv, f'MORE{i:04d}').status_code == 429
    assert caplog.text.count('exhausted') == 1


def test_operators_can_change_the_process_budget(limited_app, conv):  # noqa: F811
    limited_app.config['VOUCHER_PROCESS_FAILURE_LIMIT'] = '3 per minute'
    try:
        for i in range(3):
            assert _try(limited_app.test_client(), conv, f'GUESS{i:04d}').status_code == 200
        assert _try(limited_app.test_client(), conv, 'GUESS9999').status_code == 429
    finally:
        limited_app.config.pop('VOUCHER_PROCESS_FAILURE_LIMIT')
