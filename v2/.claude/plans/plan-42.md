# Issue #42: Admin: participants tab per conversation

**Verdict: FITS**

## Context

The roadmap section 5 ("Deferred / later") explicitly lists #42 as remaining work. No participants
tab exists on the admin conversation detail page. The data model in `db.py` provides:
- `Participation` table: `participant_id`, `conversation_id`, `accepted_at`, `new_stmt_ids`
  (list of statement IDs submitted).
- `Participant` table: `mw_username`.
- `Argument` table: `proposer_id`, `featured_statement_id` — can count per participant.
- `ArgumentVote` table: `participant_id` — can count per participant.
- No `last_seen` column exists anywhere. Adding it requires an Alembic migration.

Vote counts from Polis (per-participant) require `POLIS_DATABASE_URL` access which may not
always be available. The issue notes a fallback to local DB. A pragmatic initial version
uses only local DB data.

The admin conversation detail template (`admin_conversation.html`) has manage-card links
for Statements, Invites, and Featured. A `TODO(#165/#42)` comment exists at line ~402
pointing to where a Statistics/Participants card belongs.

## Files to change

- `v2/db.py` — add `last_seen` column to `Participation`.
- `v2/migrations/` — Alembic migration for the new column (see below).
- `v2/app.py` — add route `admin_conversation_participants` in the admin blueprint;
  update `last_seen` on each authenticated request to a conversation.
- `v2/templates/admin_conversation.html` — add a manage-card link to the new participants
  tab (at the `TODO(#165/#42)` comment, line ~402).
- `v2/templates/admin_participants.html` — new template showing the participants table.

## Implementation steps

### 1. `db.py` — add `last_seen` to `Participation`

```python
last_seen = db.Column(db.DateTime, nullable=True)
```
Add after the `revealed_at` column (~line 116).

### 2. Alembic migration

Create `v2/migrations/versions/<timestamp>_add_last_seen_to_participations.py`:

```python
"""add last_seen to participations

Revision ID: <auto>
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('participations',
        sa.Column('last_seen', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('participations', 'last_seen')
```

Generate with: `flask db migrate -m "add last_seen to participations"` then review and
`flask db upgrade`.

### 3. `app.py` — update `last_seen` on each participant page-view

In the participant blueprint's `conversation` route (or a `before_request` hook on the
participant blueprint), after the participation is retrieved, add:

```python
from datetime import datetime, timezone
participation.last_seen = datetime.now(timezone.utc)
db.session.commit()
```

This should be a best-effort update (wrap in try/except to not block the request).
Only update if the existing value is None or older than 5 minutes to avoid a DB write
on every single request.

### 4. `app.py` — new admin route `admin_conversation_participants`

Add to the admin blueprint (alongside other `admin_conversation_*` routes):

```python
@admin_bp.route('/admin/conversation/<int:conv_id>/participants')
@require_moderator
def admin_conversation_participants(conv_id):
    conversation = Conversation.query.get_or_404(conv_id)
    # Load participations with participant data.
    participations = (
        Participation.query
        .filter_by(conversation_id=conv_id)
        .join(Participant)
        .order_by(Participation.accepted_at.desc())
        .all()
    )
    # Argument counts per participant (local DB only).
    from sqlalchemy import func
    arg_counts = dict(
        db.session.query(Argument.proposer_id, func.count(Argument.id))
        .join(FeaturedStatement)
        .filter(FeaturedStatement.conversation_id == conv_id)
        .group_by(Argument.proposer_id)
        .all()
    )
    # Argument vote counts per participant.
    arg_vote_counts = dict(
        db.session.query(ArgumentVote.participant_id, func.count(ArgumentVote.id))
        .join(Argument)
        .join(FeaturedStatement)
        .filter(FeaturedStatement.conversation_id == conv_id)
        .group_by(ArgumentVote.participant_id)
        .all()
    )
    rows = []
    for p in participations:
        rows.append({
            'participation': p,
            'participant': p.participant,
            'statements_submitted': len(p.new_stmt_ids or []),
            'arguments_submitted': arg_counts.get(p.participant_id, 0),
            'arguments_voted': arg_vote_counts.get(p.participant_id, 0),
            'last_seen': p.last_seen,
        })
    return render_template(
        'admin_participants.html',
        conversation=conversation,
        rows=rows,
    )
```

Note: vote counts from Polis (statements voted / statements remaining) are not included
in this first version due to the POLIS_DATABASE_URL dependency. Add a note in the template
that Polis vote counts are not yet available.

### 5. `templates/admin_participants.html` — new template

```jinja
{% extends "base.html" %}
{% block title %}Participants — {{ conversation.title }} — wiki-polis{% endblock %}
{% block header_mode %}header--admin{% endblock %}
{% block header_crumb %}
<span class="header-crumb">
  <span class="header-crumb-sep">/</span>
  <a href="{{ url_for('admin.admin') }}">Admin</a>
  <span class="header-crumb-sep">/</span>
  <a href="{{ url_for('admin.admin_conversation_detail', conv_id=conversation.id) }}">{{ conversation.title | truncate(20, True, '…') }}</a>
  <span class="header-crumb-sep">/</span>
  <span>Participants</span>
</span>
{% endblock %}
{% block content %}
<div class="container">
  <h2>Participants — {{ conversation.title }}</h2>
  <p class="muted" style="font-size:13px;margin-bottom:1.5rem">
    {{ rows | length }} participant{{ 's' if rows | length != 1 else '' }}.
    Statement vote counts are not yet available (requires Polis database access).
  </p>
  {% if rows %}
  <table class="admin-table">
    <thead>
      <tr>
        <th>Username</th>
        <th>Joined</th>
        <th>Statements submitted</th>
        <th>Arguments submitted</th>
        <th>Arguments voted</th>
        <th>Last seen</th>
      </tr>
    </thead>
    <tbody>
      {% for row in rows %}
      <tr>
        <td>{{ row.participant.mw_username }}</td>
        <td style="white-space:nowrap">{{ row.participation.accepted_at.strftime('%Y-%m-%d') }}</td>
        <td>{{ row.statements_submitted }}</td>
        <td>{{ row.arguments_submitted }}</td>
        <td>{{ row.arguments_voted }}</td>
        <td style="white-space:nowrap">{{ row.last_seen.strftime('%Y-%m-%d %H:%M') if row.last_seen else '—' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="muted">No participants yet.</p>
  {% endif %}
</div>
{% endblock %}
```

### 6. `admin_conversation.html` — add manage-card

At the `TODO(#165/#42)` comment (~line 402), add:
```jinja
<a class="manage-card" href="{{ url_for('admin.admin_conversation_participants', conv_id=conversation.id) }}">
  <span class="manage-card-title">Participants</span>
  <span class="manage-card-meta">{{ conversation.participations | length }} joined</span>
</a>
```

## Tests

- `v2/tests/test_admin_participants.py`:
  - GET `/admin/conversation/<id>/participants` returns 200 for a moderator.
  - Response contains participant username for a known participation.
  - Returns 403 for a non-moderator.
  - `last_seen` is updated on participant page-view (fixture: visit conversation, check
    `participation.last_seen` is not None).

## Verification

1. Run `flask db upgrade` — confirm migration applies cleanly.
2. Run `pytest v2/tests/test_admin_participants.py -v`.
3. Log in as admin, navigate to a conversation detail page — verify "Participants" manage-card.
4. Click through — verify the table renders with correct counts.
5. Log in as a participant, visit the conversation — verify `last_seen` updates in the DB.
