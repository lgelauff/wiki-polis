"""store demo's fixed access answers on every demo conversation

Revision ID: e1f2a3b4c5d6
Revises: d3e4f5a6b7c8
Create Date: 2026-09-24 09:00:00.000000

A demo process has no access settings of its own: anyone may enter, nothing gates
it, everyone can see it and usernames are never shown. Until now that was implied by
``access_policy = 'demo'`` while the explicit columns could hold anything, including
a gate that the page reported as saved and the access check then ignored. This
backfill stores the fixed answers on every existing demo row; the settings service
keeps them fixed from here on (``DEMO_ACCESS_SETTINGS``).

Downgrade is a no-op: the values a demo row held before were never read (demo
overrides them in ``services/access.py``), so there is nothing to restore.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().execute(sa.text(
        """
        UPDATE conversations
        SET gated = :false_, gating_type = NULL,
            announce = :true_, information = :true_, results_shared = :true_,
            show_usernames = :false_
        WHERE access_policy = 'demo'
        """
    ), {'true_': True, 'false_': False})


def downgrade():
    pass
