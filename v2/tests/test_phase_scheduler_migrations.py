"""The phase-scheduler job must not fail while a deploy has new code but no migration yet (#456)."""

from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from db import db


_EMPTY_RUN = {'fired': 0, 'aborted': 0, 'skipped': 0, 'failed': 0}


def _stamp(app, which):
    """Record a revision in alembic_version without running migrations/env.py.

    flask_migrate.stamp() would load env.py, whose fileConfig() disables the app's loggers
    for every later test.
    """
    with app.app_context():
        script = ScriptDirectory.from_config(app.extensions['migrate'].migrate.get_config())
        head = script.get_revision(script.get_current_head())
        with db.engine.begin() as conn:
            MigrationContext.configure(conn).stamp(script, head.revision)
            if which == 'behind':                  # one migration short of the code
                revision = head.down_revision
            elif which == 'unknown':               # e.g. a rollback: the database is ahead
                revision = 'f0f0f0f0f0f0'
            else:
                revision = head.revision
            conn.execute(sa.text('UPDATE alembic_version SET version_num = :rev'), {'rev': revision})


def _run_scheduler(app):
    with patch('app._process_due_scheduled_transitions', return_value=_EMPTY_RUN) as run:
        result = app.test_cli_runner().invoke(args=['process-phase-schedules'])
    assert result.exit_code == 0, result.output
    return run


def test_scheduler_skips_and_exits_0_while_the_database_is_behind_the_code(app):
    _stamp(app, 'behind')
    _run_scheduler(app).assert_not_called()


@pytest.mark.parametrize('which', ['head', 'unknown'])
def test_scheduler_runs_when_the_database_is_at_head_or_at_a_revision_the_code_does_not_know(
        app, which):
    _stamp(app, which)
    _run_scheduler(app).assert_called_once()
