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
