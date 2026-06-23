"""add organizer conversation role (#154)

Revision ID: a4b5c6d7e8f9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b5c6d7e8f9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


old_role_type = sa.Enum('moderator', name='admin_role_type')
new_role_type = sa.Enum('moderator', 'organizer', name='admin_role_type')


def upgrade():
    with op.batch_alter_table('admin_roles', schema=None) as batch_op:
        batch_op.alter_column(
            'role',
            existing_type=old_role_type,
            type_=new_role_type,
            existing_nullable=False,
        )


def downgrade():
    op.execute("DELETE FROM admin_roles WHERE role = 'organizer'")
    with op.batch_alter_table('admin_roles', schema=None) as batch_op:
        batch_op.alter_column(
            'role',
            existing_type=new_role_type,
            type_=old_role_type,
            existing_nullable=False,
        )
