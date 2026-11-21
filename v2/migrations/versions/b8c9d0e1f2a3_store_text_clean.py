"""store plain text clean, not HTML-escaped (#616)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-21 12:00:00.000000

Until now five plain-text columns were stored nh3-escaped: "&" as "&amp;", "<" as
"&lt;", ">" as "&gt;". Text is now stored as typed and escaped only where it is shown,
so this converts the existing rows back once with html.unescape:

    arguments.body
    conversation_bans.summary, conversation_bans.lift_summary
    content_flags.detail, content_flags.resolution_note

nh3 escaped every "&" it kept, so every "&" in these columns starts an entity nh3 wrote
and one unescape gives back the typed text. Tags nh3 removed ("<b>" and the like) are
gone and cannot be restored. Only rows that contain "&" are touched; the number changed
per column is logged.

arguments.body also widens from 280 to 1000 code points: the limit stays 280 characters
as displayed (grapheme clusters), and 1000 code points is the hidden storage cap.

Before upgrading, dump the affected rows (deploy notes in the PR):
    SELECT id, body FROM arguments WHERE body LIKE '%&%';
and the same for the four other columns.

Rollback: rolling back the code alone shows "&" where "&amp;" used to be, which is the
point. A downgrade narrows arguments.body back to 280 (it fails if a longer row exists)
and does NOT escape the text again.
"""
import html
import logging

from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None

_COLUMNS = (
    ('arguments', 'body'),
    ('conversation_bans', 'summary'),
    ('conversation_bans', 'lift_summary'),
    ('content_flags', 'detail'),
    ('content_flags', 'resolution_note'),
)

log = logging.getLogger('alembic.runtime.migration')


def _unescape_column(bind, table: str, column: str) -> int:
    rows = bind.execute(sa.text(
        f'SELECT id, {column} FROM {table} WHERE {column} LIKE :amp'
    ), {'amp': '%&%'}).fetchall()
    changed = 0
    for row_id, value in rows:
        clean = html.unescape(value)
        if clean != value:
            bind.execute(sa.text(
                f'UPDATE {table} SET {column} = :value WHERE id = :id'
            ), {'value': clean, 'id': row_id})
            changed += 1
    return changed


def upgrade():
    with op.batch_alter_table('arguments') as batch:
        batch.alter_column('body', existing_type=sa.String(length=280),
                           type_=sa.String(length=1000), existing_nullable=False)
    bind = op.get_bind()
    for table, column in _COLUMNS:
        changed = _unescape_column(bind, table, column)
        log.info('#616 clean text: %s.%s: %d row(s) unescaped', table, column, changed)


def downgrade():
    with op.batch_alter_table('arguments') as batch:
        batch.alter_column('body', existing_type=sa.String(length=1000),
                           type_=sa.String(length=280), existing_nullable=False)
