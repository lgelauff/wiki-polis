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
point. A downgrade escapes the five columns again ("&" first, then "<" and ">"; U+00A0
stays as it is, the old code accepts it), so the old code shows them as before and a
later upgrade gives back exactly the text stored now. It then narrows arguments.body back
to 280. It refuses first, naming the ids, while an argument would be longer than 280
code points once escaped, so the result never depends on the database's sql_mode.
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
            # Compare-and-set: a row changed since it was read is left alone.
            result = bind.execute(sa.text(
                f'UPDATE {table} SET {column} = :value WHERE id = :id AND {column} = :old'
            ), {'value': clean, 'id': row_id, 'old': value})
            changed += result.rowcount
    return changed


def _escape(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _escape_column(bind, table: str, column: str) -> int:
    rows = bind.execute(sa.text(
        f'SELECT id, {column} FROM {table} '
        f'WHERE {column} LIKE :amp OR {column} LIKE :lt OR {column} LIKE :gt'
    ), {'amp': '%&%', 'lt': '%<%', 'gt': '%>%'}).fetchall()
    changed = 0
    for row_id, value in rows:
        result = bind.execute(sa.text(
            f'UPDATE {table} SET {column} = :value WHERE id = :id AND {column} = :old'
        ), {'value': _escape(value), 'id': row_id, 'old': value})
        changed += result.rowcount
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
    bind = op.get_bind()
    # Measured as it will be stored: escaped, the way the old code counted it.
    length = 'LENGTH' if bind.dialect.name == 'sqlite' else 'CHAR_LENGTH'
    too_long = [row_id for row_id, body in bind.execute(sa.text(
        f'SELECT id, body FROM arguments WHERE {length}(body) > 56 ORDER BY id'))
        if len(_escape(body)) > 280]
    if too_long:
        raise RuntimeError(
            'Cannot narrow arguments.body to 280: these arguments are longer: '
            + ', '.join(str(row_id) for row_id in too_long))
    for table, column in _COLUMNS:
        changed = _escape_column(bind, table, column)
        log.info('#616 clean text downgrade: %s.%s: %d row(s) escaped', table, column, changed)
    with op.batch_alter_table('arguments') as batch:
        batch.alter_column('body', existing_type=sa.String(length=1000),
                           type_=sa.String(length=280), existing_nullable=False)
