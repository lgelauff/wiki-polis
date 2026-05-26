#!/usr/bin/env python3
"""
Seed dev test users and wire them to an existing consultation.

Usage (on the dev server):
    cd ~/wiki-polis/v2
    ~/www/python/venv/bin/python seed_dev_users.py <consultation-slug>

The script is idempotent — safe to run multiple times.

What it creates:
  test-viewer      (mw_user_id=-1)  no participation
  test-participant (mw_user_id=-2)  joined the consultation, active pseudonym
  test-moderator   (mw_user_id=-3)  joined + has moderator role
  test-closed      (mw_user_id=-4)  joined a closed copy of the consultation *
                                    (* or just joined the same one if none closed)
"""

import hashlib
import sys
from app import create_app, db
from models import Participant, Participation, AdminRole, Conversation
from coolname import generate_slug

TEST_USERS = [
    {'username': 'test-viewer',      'mw_user_id': -1},
    {'username': 'test-participant', 'mw_user_id': -2},
    {'username': 'test-moderator',   'mw_user_id': -3},
    {'username': 'test-closed',      'mw_user_id': -4},
]


def get_or_create_participant(username, mw_user_id):
    p = Participant.query.filter_by(mw_user_id=mw_user_id).first()
    if p is None:
        xid = hashlib.sha256(f'dev-fake-{username}'.encode()).hexdigest()
        p = Participant(mw_user_id=mw_user_id, mw_username=username, xid=xid)
        db.session.add(p)
        db.session.flush()
        print(f'  created participant: {username} (id={p.id}, mw_user_id={mw_user_id})')
    else:
        print(f'  found participant:   {username} (id={p.id})')
    return p


def get_or_create_participation(participant, conversation):
    part = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conversation.id,
    ).first()
    if part is None:
        pseudonym = generate_slug(2)
        part = Participation(
            participant_id=participant.id,
            conversation_id=conversation.id,
            pseudonym=pseudonym,
        )
        db.session.add(part)
        db.session.flush()
        print(f'    joined conversation {conversation.slug!r} as {pseudonym!r}')
    else:
        print(f'    already joined {conversation.slug!r} as {part.pseudonym!r}')
    return part


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    slug = sys.argv[1]
    app = create_app()

    with app.app_context():
        conv = Conversation.query.filter_by(slug=slug).first()
        if conv is None:
            print(f'Error: no consultation with slug {slug!r}')
            sys.exit(1)
        print(f'Consultation: {conv.title!r} (id={conv.id}, active={conv.active})')

        # Find a closed consultation for test-closed (fall back to the given one)
        closed_conv = Conversation.query.filter_by(active=False).first() or conv

        # test-viewer: participant only, no participation
        print('\ntest-viewer:')
        get_or_create_participant('test-viewer', -1)

        # test-participant: joined the active consultation
        print('\ntest-participant:')
        p = get_or_create_participant('test-participant', -2)
        get_or_create_participation(p, conv)

        # test-moderator: joined + moderator role
        print('\ntest-moderator:')
        p = get_or_create_participant('test-moderator', -3)
        get_or_create_participation(p, conv)
        role = AdminRole.query.filter_by(
            participant_id=p.id, conversation_id=conv.id).first()
        if role is None:
            role = AdminRole(participant_id=p.id, conversation_id=conv.id)
            db.session.add(role)
            print(f'    granted moderator role on {conv.slug!r}')
        else:
            print(f'    already moderator on {conv.slug!r}')

        # test-closed: joined a closed consultation
        print('\ntest-closed:')
        p = get_or_create_participant('test-closed', -4)
        if closed_conv.id != conv.id:
            print(f'  using closed consultation: {closed_conv.title!r}')
        else:
            print('  no closed consultation found — using the same one')
        get_or_create_participation(p, closed_conv)

        db.session.commit()
        print('\nDone.')


if __name__ == '__main__':
    main()
