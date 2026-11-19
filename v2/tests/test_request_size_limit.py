"""The 2 MB request body cap (MAX_CONTENT_LENGTH).

Werkzeug 3.1.9 no longer caps urlencoded form bodies with max_form_memory_size, so
without an app-wide cap a form post of any size is parsed into memory. These tests
pin the cap for an HTML form and a JSON API post, and check that the largest bulk
request the admin console sends still fits well under it.
"""

import json
from unittest.mock import MagicMock, patch

from db import db
from seed_csv import MAX_ROWS, MAX_TEXT_CHARS

LIMIT = 2 * 1024 * 1024


def _voucher_conversation(conversation):
    conversation.gated = True
    conversation.gating_type = 'voucher'
    db.session.commit()
    return conversation


def _form_body(size: int) -> bytes:
    """A urlencoded form body of exactly ``size`` bytes."""
    prefix = b'code='
    return prefix + b'A' * (size - len(prefix))


def _json_body(size: int) -> bytes:
    """A JSON object body of exactly ``size`` bytes."""
    head, tail = b'{"statements": ["', b'"]}'
    return head + b'a' * (size - len(head) - len(tail)) + tail


def test_a_form_post_just_under_the_limit_is_not_refused_for_size(client, conversation):
    conv = _voucher_conversation(conversation)

    response = client.post(
        f'/c/{conv.slug}/v', data=_form_body(LIMIT - 1024),
        content_type='application/x-www-form-urlencoded',
    )

    assert response.status_code != 413


def test_a_form_post_over_the_limit_is_refused_with_413(client, conversation):
    conv = _voucher_conversation(conversation)

    response = client.post(
        f'/c/{conv.slug}/v', data=_form_body(LIMIT + 1),
        content_type='application/x-www-form-urlencoded',
    )

    assert response.status_code == 413
    assert not response.is_json


def test_a_json_api_post_just_under_the_limit_is_not_refused_for_size(
    admin_client, conversation,
):
    response = admin_client.post(
        f'/api/v1/admin/conversations/{conversation.id}/statement-imports',
        data=_json_body(LIMIT - 1024), content_type='application/json',
    )

    # Refused, but by validation (one statement far over 280 characters), not by size.
    assert response.status_code != 413
    assert response.is_json


def test_a_json_api_post_over_the_limit_gets_the_json_413_envelope(
    admin_client, conversation,
):
    response = admin_client.post(
        f'/api/v1/admin/conversations/{conversation.id}/statement-imports',
        data=_json_body(LIMIT + 1), content_type='application/json',
    )

    assert response.status_code == 413
    assert response.is_json
    assert response.get_json()['error']['code'] == 'payload_too_large'


def test_the_largest_seed_import_still_fits_under_the_limit(admin_client, conversation):
    """The textarea import at its caps: MAX_ROWS statements of MAX_TEXT_CHARS
    characters each, in a script that JSON escapes to 6 bytes a character."""
    statements = [f'{i:02d}' + 'ж' * (MAX_TEXT_CHARS - 2) for i in range(MAX_ROWS)]
    body = json.dumps({'statements': statements}).encode()
    assert len(body) < LIMIT // 50  # about 34 kB: the cap is far above it
    server = MagicMock()
    server.get_statements.return_value = ([], [], [])
    server.bulk_add_seeds.return_value = (MAX_ROWS, [], 0)
    participant = MagicMock()
    participant.get_settings.return_value = {'strict_moderation': True}
    participant.get_statements.return_value = ([], [], [])
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.post(
            f'/api/v1/admin/conversations/{conversation.id}/statement-imports',
            data=body, content_type='application/json',
        )

    assert response.status_code == 200
    assert response.get_json()['data']['outcome']['imported'] == MAX_ROWS
