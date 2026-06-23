"""store argument proposer pseudonym (#113)

Revision ID: 5c7d8e9f0123
Revises: 4b6c7d8e9f01
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c7d8e9f0123'
down_revision = '4b6c7d8e9f01'
branch_labels = None
depends_on = None


def _drop_fk_for_column(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys(table_name):
        if fk.get('constrained_columns') == [column_name] and fk.get('name'):
            op.drop_constraint(fk['name'], table_name, type_='foreignkey')


def _drop_unique_for_columns(table_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for uq in inspector.get_unique_constraints(table_name):
        if uq.get('column_names') == columns and uq.get('name'):
            op.drop_constraint(uq['name'], table_name, type_='unique')


def upgrade():
    op.add_column('arguments', sa.Column('proposer_pseudonym', sa.String(length=80),
                                         nullable=True))

    op.execute("""
        UPDATE arguments
           SET proposer_pseudonym = (
               SELECT participations.pseudonym
                 FROM featured_statements
                 JOIN participations
                   ON participations.conversation_id = featured_statements.conversation_id
                  AND participations.participant_id = arguments.proposer_id
                WHERE featured_statements.id = arguments.featured_statement_id
                LIMIT 1
           )
         WHERE proposer_id IS NOT NULL
    """)

    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('arguments', recreate='always') as batch:
            # Drop the index on proposer_id first, or batch table-recreation tries
            # to rebuild it against the column we're about to remove.
            batch.drop_index('ix_arguments_proposer_id')
            batch.drop_column('proposer_id')
            batch.create_unique_constraint(
                'uq_arguments_featured_pseudonym_side',
                ['featured_statement_id', 'proposer_pseudonym', 'side'],
            )
    else:
        # Drop the FK before its backing index — MySQL refuses to drop an index
        # that is still needed by a foreign-key constraint (error 1553).
        _drop_fk_for_column('arguments', 'proposer_id')
        op.drop_index('ix_arguments_proposer_id', table_name='arguments')
        _drop_unique_for_columns(
            'arguments',
            ['featured_statement_id', 'proposer_id', 'side'],
        )
        op.drop_column('arguments', 'proposer_id')
        op.create_unique_constraint(
            'uq_arguments_featured_pseudonym_side',
            'arguments',
            ['featured_statement_id', 'proposer_pseudonym', 'side'],
        )
    op.create_index('ix_arguments_proposer_pseudonym', 'arguments',
                    ['proposer_pseudonym'])


def downgrade():
    op.add_column('arguments', sa.Column('proposer_id', sa.Integer(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.drop_index('ix_arguments_proposer_pseudonym', table_name='arguments')
        op.drop_constraint('uq_arguments_featured_pseudonym_side', 'arguments',
                           type_='unique')
        op.create_foreign_key(None, 'arguments', 'participants',
                              ['proposer_id'], ['id'], ondelete='SET NULL')
        op.create_unique_constraint(None, 'arguments',
                                    ['featured_statement_id', 'proposer_id', 'side'])
        op.create_index('ix_arguments_proposer_id', 'arguments', ['proposer_id'])
        op.drop_column('arguments', 'proposer_pseudonym')
        return

    with op.batch_alter_table('arguments', recreate='always') as batch:
        batch.drop_column('proposer_pseudonym')
        batch.create_unique_constraint(None, ['featured_statement_id', 'proposer_id', 'side'])
    op.create_index('ix_arguments_proposer_id', 'arguments', ['proposer_id'])
